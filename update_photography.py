#!/usr/bin/env python3
"""
update_photography.py  —  Rebuild the Photography gallery on the site.

What it does:
  1. (Optional) Import photos from a source folder.
     - Skips videos and JSON files.
     - Prefers *-edited copies over originals when both are present.
     - Extracts GPS from Google Takeout .supplemental-metadata.json sidecars,
       falling back to EXIF. Reverse-geocodes via Nominatim (OpenStreetMap).
     - Saves location data to images/photography/metadata.json.
  2. Rewrites the <!-- GALLERY:START ... GALLERY:END --> block in
     photography.html, embedding data-lat / data-lng / data-location
     attributes for photos that have location metadata.

Usage
-----
    # Regenerate HTML from current photos + metadata:
    python3 update_photography.py

    # Import new photos (HEICs converted automatically):
    python3 update_photography.py --import ~/Desktop/new_photos

    # Import and wipe existing photos first:
    python3 update_photography.py --import ~/Desktop/new_photos --fresh

    # Import without reverse-geocoding (faster, coords only):
    python3 update_photography.py --import ~/Desktop/new_photos --no-geocode

    # Manually set a location for one photo:
    python3 update_photography.py --locate photo_05.jpg "Big Sur, CA"
    python3 update_photography.py --locate photo_05.jpg "Big Sur" 36.27 -121.81

Requires: pip install pillow pillow-heif
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parent
PHOTO_DIR  = REPO_ROOT / "images" / "photography"
HTML_FILE  = REPO_ROOT / "photography.html"
META_FILE  = PHOTO_DIR / "metadata.json"

IMAGE_EXTS  = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
VIDEO_EXTS  = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".wmv", ".webm"}
EDIT_SUFFIXES = ("-edited", "-edit")   # checked case-insensitively
MAX_SIDE    = 1800
JPEG_QUALITY = 85

GALLERY_START = "<!-- GALLERY:START -->"
GALLERY_END   = "<!-- GALLERY:END -->"

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
NOMINATIM_UA  = "tejank10-photography-site/1.0 (tejan@stanford.edu)"


# ── Pillow loader ──────────────────────────────────────────────────────────

def _load_pillow():
    try:
        from PIL import Image, ExifTags  # noqa: F401
    except ImportError:
        sys.exit("Pillow not installed. Run:  pip install pillow pillow-heif")
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    from PIL import Image, ExifTags
    return Image, ExifTags


# ── Image helpers ──────────────────────────────────────────────────────────

def _fix_orientation(img, ExifTags):
    try:
        exif = img._getexif() or {}
        for k, v in ExifTags.TAGS.items():
            if v == "Orientation":
                o = exif.get(k)
                if o == 3:   img = img.rotate(180, expand=True)
                elif o == 6: img = img.rotate(270, expand=True)
                elif o == 8: img = img.rotate(90,  expand=True)
                break
    except Exception:
        pass
    return img


def _dms_to_deg(dms, ref: str):
    if not dms or not ref:
        return None
    try:
        d, m, s = [float(x) for x in dms]
        deg = d + m / 60.0 + s / 3600.0
        if ref.upper() in ("S", "W"):
            deg = -deg
        return round(deg, 6)
    except Exception:
        return None


def _extract_gps_exif(img, ExifTags):
    try:
        from PIL.ExifTags import GPSTAGS
        exif = img._getexif() or {}
        for tag_id, value in exif.items():
            if ExifTags.TAGS.get(tag_id) == "GPSInfo":
                gps = {GPSTAGS.get(k, k): v for k, v in value.items()}
                lat = _dms_to_deg(gps.get("GPSLatitude"),  gps.get("GPSLatitudeRef"))
                lng = _dms_to_deg(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
                if lat is not None and lng is not None:
                    return lat, lng
    except Exception:
        pass
    return None, None


# ── Edit-suffix helpers ────────────────────────────────────────────────────

def _is_edited(stem: str) -> bool:
    low = stem.lower()
    return any(low.endswith(s) for s in EDIT_SUFFIXES)


def _base_stem(stem: str) -> str:
    low = stem.lower()
    for s in EDIT_SUFFIXES:
        if low.endswith(s):
            return stem[: -len(s)]
    return stem


# ── Google Takeout sidecar GPS ─────────────────────────────────────────────

def _gps_from_sidecar(src: Path):
    orig_stem = _base_stem(src.stem)
    orig_name = orig_stem + src.suffix
    candidates = [
        src.parent / (src.name + ".supplemental-metadata.json"),
        src.parent / (src.name + ".json"),
        src.parent / (src.stem + ".json"),
        src.parent / (orig_name + ".supplemental-metadata.json"),
        src.parent / (orig_name + ".json"),
        src.parent / (orig_stem + ".json"),
    ]
    seen = set()
    for sc in candidates:
        if sc in seen or not sc.exists():
            seen.add(sc); continue
        seen.add(sc)
        try:
            data = json.loads(sc.read_text(encoding="utf-8"))
            for key in ("geoDataExif", "geoData"):
                geo = data.get(key, {})
                lat, lng = geo.get("latitude"), geo.get("longitude")
                if lat is not None and lng is not None and (lat != 0.0 or lng != 0.0):
                    return round(float(lat), 6), round(float(lng), 6)
        except Exception:
            pass
    return None, None


# ── Nominatim geocoding ────────────────────────────────────────────────────

def _reverse_geocode(lat: float, lng: float) -> str:
    url = (f"{NOMINATIM_URL}/reverse?lat={lat}&lon={lng}"
           f"&format=json&zoom=10&addressdetails=1")
    req = urllib.request.Request(url, headers={"User-Agent": NOMINATIM_UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        addr = data.get("address", {})
        place = (addr.get("city") or addr.get("town") or addr.get("village")
                 or addr.get("municipality") or addr.get("county")
                 or addr.get("state") or "")
        country = addr.get("country", "")
        parts = [p for p in [place, country] if p]
        return ", ".join(parts) if parts else f"{lat}, {lng}"
    except Exception as e:
        print(f"    [geocode] warning: {e}")
        return f"{lat}, {lng}"


def _forward_geocode(place: str):
    url = (f"{NOMINATIM_URL}/search"
           f"?q={urllib.parse.quote(place)}&format=json&limit=1")
    req = urllib.request.Request(url, headers={"User-Agent": NOMINATIM_UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            results = json.loads(r.read())
        if results:
            return round(float(results[0]["lat"]), 6), round(float(results[0]["lon"]), 6)
    except Exception as e:
        print(f"  [geocode] warning: {e}")
    return None, None


# ── metadata.json I/O ──────────────────────────────────────────────────────

def _load_meta() -> dict:
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_meta(meta: dict) -> None:
    META_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False))


# ── Import ─────────────────────────────────────────────────────────────────

def import_photos(source: Path, fresh: bool, geocode: bool) -> None:
    Image, ExifTags = _load_pillow()

    if not source.is_dir():
        sys.exit(f"Source folder not found: {source}")

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    if fresh:
        for f in PHOTO_DIR.glob("photo_*.jpg"):
            f.unlink()
        print(f"Cleared {PHOTO_DIR}")

    meta = _load_meta()

    existing = sorted(PHOTO_DIR.glob("photo_*.jpg"))
    next_idx = 1
    for f in existing:
        m = re.match(r"photo_(\d+)\.jpg$", f.name)
        if m:
            next_idx = max(next_idx, int(m.group(1)) + 1)

    all_images = [
        p for p in source.iterdir()
        if p.is_file()
        and p.suffix.lower() in IMAGE_EXTS
        and p.suffix.lower() not in VIDEO_EXTS
    ]

    # Find stems that have an edited counterpart
    edited_bases = {_base_stem(p.stem).lower() for p in all_images if _is_edited(p.stem)}

    def _keep(p: Path) -> bool:
        if _is_edited(p.stem):       return True   # always keep edited
        if p.stem.lower() in edited_bases: return False  # original has edit, skip
        return True

    sources = sorted(p for p in all_images if _keep(p))
    skipped = len(all_images) - len(sources)
    if skipped:
        print(f"  (skipping {skipped} original(s) that have an edited copy)")
    if not sources:
        print(f"No images found in {source}"); return

    for src in sources:
        try:
            img = Image.open(src)
            lat, lng = _gps_from_sidecar(src)
            if lat is None:
                lat, lng = _extract_gps_exif(img, ExifTags)

            img = _fix_orientation(img, ExifTags)
            img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > MAX_SIDE:
                scale = MAX_SIDE / max(w, h)
                img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)

            dst_name = f"photo_{next_idx:02d}.jpg"
            dst = PHOTO_DIR / dst_name
            img.save(dst, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)

            tag = " [edited]" if _is_edited(src.stem) else ""
            if lat is not None:
                location = ""
                if geocode:
                    print(f"  {src.name}{tag}  ->  {dst_name}  [{lat:.4f}, {lng:.4f}]  geocoding...")
                    location = _reverse_geocode(lat, lng)
                    time.sleep(1.1)
                    print(f"    location: {location}")
                else:
                    print(f"  {src.name}{tag}  ->  {dst_name}  [{lat:.4f}, {lng:.4f}]")
                meta[dst_name] = {"lat": lat, "lng": lng, "location": location}
            else:
                print(f"  {src.name}{tag}  ->  {dst_name}  (no GPS)")
                meta.setdefault(dst_name, {})

            next_idx += 1
        except Exception as e:
            print(f"  SKIP {src.name}: {e}")

    _save_meta(meta)
    print(f"Saved metadata to {META_FILE}")


# ── Manual locate ──────────────────────────────────────────────────────────

def set_location(photo: str, label: str, lat, lng) -> None:
    name = Path(photo).name
    if not name.endswith(".jpg"):
        name = Path(name).stem + ".jpg"
    target = PHOTO_DIR / name
    if not target.exists():
        available = ", ".join(p.name for p in sorted(PHOTO_DIR.glob("photo_*.jpg")))
        sys.exit(f"Photo not found: {target}\nAvailable: {available}")

    if lat is None or lng is None:
        print(f'  Geocoding "{label}"...')
        lat, lng = _forward_geocode(label)
        if lat is None:
            sys.exit(f'Could not geocode "{label}". Try providing explicit lat/lng.')
        print(f"  Resolved to {lat:.4f}, {lng:.4f}")

    meta = _load_meta()
    meta[name] = {"lat": lat, "lng": lng, "location": label}
    _save_meta(meta)
    print(f'  Set {name} -> "{label}" ({lat}, {lng})')


# ── HTML rebuild ───────────────────────────────────────────────────────────

def _natural_key(path: Path):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", path.name)]


def rebuild_html() -> None:
    if not HTML_FILE.exists():
        sys.exit(f"{HTML_FILE} not found")

    photos = sorted(
        [p for p in PHOTO_DIR.iterdir()
         if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}],
        key=_natural_key,
    )
    if not photos:
        print("No photos in images/photography/ — nothing to write."); return

    meta = _load_meta()

    lines = []
    for i, p in enumerate(photos):
        rel   = f"images/photography/{p.name}"
        entry = meta.get(p.name, {})
        lat   = entry.get("lat")
        lng   = entry.get("lng")
        loc   = entry.get("location", "")

        attrs = ""
        if lat is not None and lng is not None:
            attrs += f' data-lat="{lat}" data-lng="{lng}"'
        if loc:
            attrs += f' data-location="{loc.replace(chr(34), "&quot;")}"'

        lines.append(
            f'      <div class="gallery-item" onclick="openLightbox({i})"{attrs}>'
            f'<img src="{rel}" alt="" loading="lazy"></div>'
        )

    new_block = (
        f"{GALLERY_START}\n"
        + "\n".join(lines)
        + f"\n      {GALLERY_END}"
    )

    html = HTML_FILE.read_text()
    pattern = re.compile(
        re.escape(GALLERY_START) + r".*?" + re.escape(GALLERY_END), re.DOTALL
    )
    if not pattern.search(html):
        sys.exit("Could not find GALLERY:START / GALLERY:END markers in "
                 f"{HTML_FILE.name}.")
    HTML_FILE.write_text(pattern.sub(new_block, html))
    tagged = sum(1 for p in photos if meta.get(p.name, {}).get("location"))
    print(f"Wrote {len(photos)} photos ({tagged} with location) into {HTML_FILE.name}")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--import", dest="source", type=Path, default=None,
                    help="Folder of photos to import.")
    ap.add_argument("--fresh", action="store_true",
                    help="Delete existing photos before importing.")
    ap.add_argument("--no-geocode", dest="geocode", action="store_false", default=True,
                    help="Skip reverse-geocoding (store coords only).")
    ap.add_argument("--locate", nargs="+", metavar="ARG",
                    help=("Set location for a photo: "
                          "--locate photo_05.jpg \"Big Sur, CA\" [lat lng]"))
    args = ap.parse_args()

    if args.locate:
        parts = args.locate
        if len(parts) < 2:
            ap.error("--locate requires at least PHOTO and LABEL")
        set_location(
            parts[0], parts[1],
            float(parts[2]) if len(parts) > 2 else None,
            float(parts[3]) if len(parts) > 3 else None,
        )

    if args.source is not None:
        import_photos(args.source.expanduser(), args.fresh, args.geocode)

    rebuild_html()


if __name__ == "__main__":
    main()
