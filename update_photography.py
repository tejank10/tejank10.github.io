#!/usr/bin/env python3
"""
update_photography.py  —  Rebuild the Photography gallery on the site.

Two things it does:

1.  (Optional) Import photos from a source folder.
    Any .jpg/.jpeg/.png/.heic there is converted to JPEG, EXIF-rotated,
    resized to max 1800px on the long side, and copied into
    images/photography/ with sequential filenames (photo_NN.jpg).

2.  Rewrites the <!-- GALLERY:START ... GALLERY:END --> block in
    photography.html so it lists every photo currently in
    images/photography/ (sorted by filename).

Usage
-----
    # Just regenerate the HTML from whatever's already in images/photography/:
    python3 update_photography.py

    # Import new photos from a folder (HEICs get converted automatically),
    # then regenerate the HTML:
    python3 update_photography.py --import ~/Desktop/new_photos

    # Wipe images/photography/ before importing (useful if you want to
    # re-curate from scratch):
    python3 update_photography.py --import ~/Desktop/new_photos --fresh

Requires: pip install pillow pillow-heif   (pillow-heif only needed for HEIC)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PHOTO_DIR = REPO_ROOT / "images" / "photography"
HTML_FILE = REPO_ROOT / "photography.html"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
MAX_SIDE = 1800
JPEG_QUALITY = 85

GALLERY_START = "<!-- GALLERY:START -->"
GALLERY_END = "<!-- GALLERY:END -->"


# --- image pipeline ------------------------------------------------------

def _load_pillow():
    try:
        from PIL import Image, ExifTags  # noqa: F401
    except ImportError:
        sys.exit("Pillow not installed. Run:  pip install pillow pillow-heif")
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass  # HEIC support is optional
    from PIL import Image, ExifTags
    return Image, ExifTags


def _fix_orientation(img, ExifTags):
    """Apply EXIF orientation so the saved JPEG faces the right way."""
    try:
        exif = img._getexif() or {}
        for k, v in ExifTags.TAGS.items():
            if v == "Orientation":
                o = exif.get(k)
                if o == 3:
                    img = img.rotate(180, expand=True)
                elif o == 6:
                    img = img.rotate(270, expand=True)
                elif o == 8:
                    img = img.rotate(90, expand=True)
                break
    except Exception:
        pass
    return img


def import_photos(source: Path, fresh: bool) -> None:
    Image, ExifTags = _load_pillow()

    if not source.is_dir():
        sys.exit(f"Source folder not found: {source}")

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    if fresh:
        for f in PHOTO_DIR.glob("photo_*.jpg"):
            f.unlink()
        print(f"Cleared {PHOTO_DIR}")

    # Next available index, so re-imports append rather than overwrite.
    existing = sorted(PHOTO_DIR.glob("photo_*.jpg"))
    next_idx = 1
    for f in existing:
        m = re.match(r"photo_(\d+)\.jpg$", f.name)
        if m:
            next_idx = max(next_idx, int(m.group(1)) + 1)

    sources = sorted(
        p for p in source.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    if not sources:
        print(f"No images found in {source}")
        return

    for src in sources:
        try:
            img = Image.open(src)
            img = _fix_orientation(img, ExifTags)
            img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > MAX_SIDE:
                if w >= h:
                    img = img.resize((MAX_SIDE, round(h * MAX_SIDE / w)), Image.LANCZOS)
                else:
                    img = img.resize((round(w * MAX_SIDE / h), MAX_SIDE), Image.LANCZOS)
            dst = PHOTO_DIR / f"photo_{next_idx:02d}.jpg"
            img.save(dst, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            print(f"  {src.name}  ->  {dst.name}   {img.size}")
            next_idx += 1
        except Exception as e:
            print(f"  SKIP {src.name}: {e}")


# --- HTML rewrite --------------------------------------------------------

def _natural_key(path: Path):
    """photo_2.jpg < photo_10.jpg"""
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
        print("No photos in images/photography/ — nothing to write.")
        return

    lines = []
    for i, p in enumerate(photos):
        rel = f"images/photography/{p.name}"
        lines.append(
            f'      <div class="gallery-item" onclick="openLightbox({i})">'
            f'<img src="{rel}" alt="" loading="lazy"></div>'
        )

    new_block = (
        f"{GALLERY_START}\n"
        + "\n".join(lines)
        + f"\n      {GALLERY_END}"
    )

    html = HTML_FILE.read_text()
    pattern = re.compile(
        re.escape(GALLERY_START) + r".*?" + re.escape(GALLERY_END),
        re.DOTALL,
    )
    if not pattern.search(html):
        sys.exit(
            "Could not find GALLERY:START / GALLERY:END markers in "
            f"{HTML_FILE.name}. Add them back around the gallery-item block."
        )
    html = pattern.sub(new_block, html)
    HTML_FILE.write_text(html)
    print(f"Wrote {len(photos)} photos into {HTML_FILE.name}")


# --- CLI -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--import", dest="source", type=Path, default=None,
        help="Folder of new photos to convert & copy into images/photography/",
    )
    ap.add_argument(
        "--fresh", action="store_true",
        help="With --import, delete existing images/photography/*.jpg first.",
    )
    args = ap.parse_args()

    if args.source is not None:
        import_photos(args.source.expanduser(), args.fresh)

    rebuild_html()


if __name__ == "__main__":
    main()
