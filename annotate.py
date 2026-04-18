#!/usr/bin/env python3
"""
annotate.py — Local web app for annotating photo locations.

Usage:
    python3 annotate.py          # starts on http://localhost:8090
    python3 annotate.py --port 9000
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parent
PHOTO_DIR  = REPO_ROOT / "images" / "photography"
META_PATH  = PHOTO_DIR / "metadata.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_meta() -> dict:
    if META_PATH.exists():
        try:
            return json.loads(META_PATH.read_text())
        except Exception:
            pass
    return {}

def save_meta(meta: dict) -> None:
    META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False))

def photo_list() -> list[str]:
    def key(p):
        m = re.search(r"(\d+)", p.stem)
        return int(m.group(1)) if m else 0
    return [p.name for p in sorted(PHOTO_DIR.glob("photo_*.jpg"), key=key)]

# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Photo Annotator</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         font-size: 14px; background: #f5f5f5; color: #222; height: 100vh;
         display: flex; flex-direction: column; overflow: hidden; }

  /* ── top bar ── */
  header { background: #1a1a2e; color: #fff; padding: 10px 20px;
           display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
  header h1 { font-size: 1rem; font-weight: 600; letter-spacing: .02em; }
  header .spacer { flex: 1; }
  .btn { padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer;
         font-size: 13px; font-weight: 500; transition: opacity .15s; }
  .btn:hover { opacity: .85; }
  .btn-primary   { background: #4f8ef7; color: #fff; }
  .btn-success   { background: #3dba6f; color: #fff; }
  .btn-secondary { background: #555; color: #fff; }
  #status { font-size: 12px; opacity: .8; min-width: 180px; text-align: right; }

  /* ── layout ── */
  .body { display: flex; flex: 1; overflow: hidden; }

  /* ── left: grid ── */
  .grid-panel { width: 340px; flex-shrink: 0; overflow-y: auto;
                background: #fff; border-right: 1px solid #ddd; padding: 12px; }
  .grid-panel h2 { font-size: .78rem; text-transform: uppercase; letter-spacing: .08em;
                   color: #888; margin-bottom: 10px; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
  .thumb { position: relative; cursor: pointer; border-radius: 4px; overflow: hidden;
           border: 2px solid transparent; aspect-ratio: 1; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block;
               transition: opacity .15s; }
  .thumb:hover img { opacity: .8; }
  .thumb.tagged  { border-color: #3dba6f; }
  .thumb.active  { border-color: #4f8ef7; box-shadow: 0 0 0 2px #4f8ef766; }
  .thumb .badge  { position: absolute; bottom: 3px; right: 3px;
                   background: rgba(0,0,0,.55); border-radius: 3px;
                   padding: 1px 4px; font-size: 9px; color: #fff; }
  .thumb .num    { position: absolute; top: 3px; left: 4px;
                   font-size: 9px; color: #fff; background: rgba(0,0,0,.4);
                   border-radius: 3px; padding: 1px 4px; }

  /* ── right: editor ── */
  .editor-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  .editor-panel .placeholder { flex: 1; display: flex; align-items: center;
                                justify-content: center; color: #aaa; font-size: .9rem; }
  .editor { display: none; flex: 1; flex-direction: column; }
  .editor.visible { display: flex; }

  .preview { height: 200px; flex-shrink: 0; background: #111;
             display: flex; align-items: center; justify-content: center; overflow: hidden; }
  .preview img { max-height: 100%; max-width: 100%; object-fit: contain; }

  .fields { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px;
            border-bottom: 1px solid #eee; flex-shrink: 0; }
  .field label { display: block; font-size: .75rem; font-weight: 600;
                 text-transform: uppercase; letter-spacing: .06em; color: #666;
                 margin-bottom: 4px; }
  .field input { width: 100%; padding: 7px 10px; border: 1px solid #ccc;
                 border-radius: 6px; font-size: 13px; outline: none; }
  .field input:focus { border-color: #4f8ef7; box-shadow: 0 0 0 2px #4f8ef722; }
  .row { display: flex; gap: 10px; }
  .row .field { flex: 1; }
  .action-row { display: flex; gap: 8px; align-items: center; }
  .action-row .hint { font-size: 11px; color: #999; flex: 1; }

  #map { flex: 1; min-height: 200px; }
  .map-hint { font-size: 11px; color: #888; padding: 6px 20px;
              border-bottom: 1px solid #eee; background: #fafafa; flex-shrink: 0; }

  /* ── search box over map ── */
  .search-wrap { padding: 10px 20px 0; flex-shrink: 0; display: flex; gap: 8px; }
  .search-wrap input { flex: 1; padding: 7px 10px; border: 1px solid #ccc;
                       border-radius: 6px; font-size: 13px; outline: none; }
  .search-wrap input:focus { border-color: #4f8ef7; }
</style>
</head>
<body>

<header>
  <h1>📍 Photo Location Annotator</h1>
  <span class="spacer"></span>
  <span id="status">No photo selected</span>
  <button class="btn btn-success" onclick="rebuildHtml()">Rebuild site HTML</button>
</header>

<div class="body">
  <!-- Grid -->
  <div class="grid-panel">
    <h2>Photos (<span id="total">0</span> total · <span id="ntagged">0</span> tagged)</h2>
    <div class="grid" id="grid"></div>
  </div>

  <!-- Editor -->
  <div class="editor-panel">
    <div class="placeholder" id="placeholder">← Select a photo to annotate</div>

    <div class="editor" id="editor">
      <div class="preview"><img id="preview-img" src="" alt=""></div>

      <div class="fields">
        <div class="field">
          <label>Location Name (shown on hover)</label>
          <input id="f-location" type="text" placeholder="e.g. Yosemite Valley, CA">
        </div>
        <div class="row">
          <div class="field">
            <label>Latitude</label>
            <input id="f-lat" type="number" step="any" placeholder="37.7456">
          </div>
          <div class="field">
            <label>Longitude</label>
            <input id="f-lng" type="number" step="any" placeholder="-119.5936">
          </div>
        </div>
        <div class="action-row">
          <button class="btn btn-primary" onclick="savePhoto()">Save</button>
          <button class="btn btn-secondary" onclick="clearPhoto()">Clear location</button>
          <span class="hint">Tip: click the map or search to set coordinates</span>
        </div>
      </div>

      <!-- Map search -->
      <div class="search-wrap">
        <input id="search-input" type="text" placeholder="Search a place to jump the map…">
        <button class="btn btn-secondary" onclick="searchPlace()">Go</button>
      </div>
      <div class="map-hint">Click the map to set coordinates · drag the marker to adjust</div>
      <div id="map"></div>
    </div>
  </div>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let photos = [];
let meta   = {};
let current = null;  // currently selected photo name
let marker  = null;

// ── Init ──────────────────────────────────────────────────────────────────
async function init() {
  const [pRes, mRes] = await Promise.all([fetch('/api/photos'), fetch('/api/metadata')]);
  photos = await pRes.json();
  meta   = await mRes.json();
  renderGrid();
}

// ── Grid ──────────────────────────────────────────────────────────────────
function renderGrid() {
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  let tagged = 0;
  photos.forEach((name, i) => {
    const e = meta[name] || {};
    const isTagged = !!(e.location || e.lat);
    if (isTagged) tagged++;
    const div = document.createElement('div');
    div.className = 'thumb' + (isTagged ? ' tagged' : '') + (name === current ? ' active' : '');
    div.dataset.name = name;
    div.innerHTML = `
      <span class="num">${i + 1}</span>
      <img src="/photo/${name}" loading="lazy">
      ${isTagged ? `<span class="badge">📍</span>` : ''}`;
    div.onclick = () => selectPhoto(name);
    grid.appendChild(div);
  });
  document.getElementById('total').textContent = photos.length;
  document.getElementById('ntagged').textContent = tagged;
}

// ── Select photo ──────────────────────────────────────────────────────────
function selectPhoto(name) {
  current = name;
  document.querySelectorAll('.thumb').forEach(t =>
    t.classList.toggle('active', t.dataset.name === name));

  const e = meta[name] || {};
  document.getElementById('f-location').value = e.location || '';
  document.getElementById('f-lat').value = e.lat != null ? e.lat : '';
  document.getElementById('f-lng').value = e.lng != null ? e.lng : '';
  document.getElementById('preview-img').src = '/photo/' + name;
  document.getElementById('status').textContent = name;

  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('editor').classList.add('visible');

  // Init map once
  if (!window._mapInit) initMap();

  const lat = parseFloat(e.lat) || 37.7749;
  const lng = parseFloat(e.lng) || -122.4194;
  const hasCoords = e.lat != null;
  map.setView([lat, lng], hasCoords ? 13 : 5);
  placeMarker(lat, lng, !hasCoords);
}

// ── Leaflet map ────────────────────────────────────────────────────────────
let map;
function initMap() {
  window._mapInit = true;
  map = L.map('map').setView([37.7749, -122.4194], 5);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors', maxZoom: 19
  }).addTo(map);

  map.on('click', e => {
    const {lat, lng} = e.latlng;
    document.getElementById('f-lat').value = lat.toFixed(6);
    document.getElementById('f-lng').value = lng.toFixed(6);
    placeMarker(lat, lng);
  });
}

function placeMarker(lat, lng, ghost = false) {
  if (marker) marker.remove();
  if (ghost) return;
  marker = L.marker([lat, lng], {draggable: true}).addTo(map);
  marker.on('dragend', e => {
    const {lat, lng} = e.target.getLatLng();
    document.getElementById('f-lat').value = lat.toFixed(6);
    document.getElementById('f-lng').value = lng.toFixed(6);
  });
}

// ── Search ────────────────────────────────────────────────────────────────
async function searchPlace() {
  const q = document.getElementById('search-input').value.trim();
  if (!q) return;
  const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1`;
  try {
    const res = await fetch(url, {headers: {'User-Agent': 'tejank10-annotator/1.0'}});
    const data = await res.json();
    if (!data.length) { alert('Place not found'); return; }
    const {lat, lon, display_name} = data[0];
    document.getElementById('f-lat').value = parseFloat(lat).toFixed(6);
    document.getElementById('f-lng').value = parseFloat(lon).toFixed(6);
    if (!document.getElementById('f-location').value)
      document.getElementById('f-location').value = display_name.split(',').slice(0,2).join(',').trim();
    map.setView([lat, lon], 13);
    placeMarker(parseFloat(lat), parseFloat(lon));
  } catch(e) { alert('Search failed: ' + e.message); }
}

document.addEventListener('keydown', e => {
  if (e.target.id === 'search-input' && e.key === 'Enter') searchPlace();
  if (e.target.id === 'f-location' && e.key === 'Enter') savePhoto();
});

// ── Save / Clear ───────────────────────────────────────────────────────────
async function savePhoto() {
  if (!current) return;
  const location = document.getElementById('f-location').value.trim();
  const lat = parseFloat(document.getElementById('f-lat').value) || null;
  const lng = parseFloat(document.getElementById('f-lng').value) || null;

  meta[current] = {lat, lng, location};
  await fetch('/api/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(meta)
  });

  // Update marker
  if (lat && lng) { map.setView([lat, lng], map.getZoom()); placeMarker(lat, lng); }

  renderGrid();
  document.getElementById('status').textContent = `Saved ${current} ✓`;
  setTimeout(() => document.getElementById('status').textContent = current, 1500);
}

async function clearPhoto() {
  if (!current) return;
  meta[current] = {lat: null, lng: null, location: ''};
  document.getElementById('f-location').value = '';
  document.getElementById('f-lat').value = '';
  document.getElementById('f-lng').value = '';
  if (marker) { marker.remove(); marker = null; }
  await fetch('/api/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(meta)
  });
  renderGrid();
}

// ── Rebuild HTML ───────────────────────────────────────────────────────────
async function rebuildHtml() {
  document.getElementById('status').textContent = 'Rebuilding…';
  await fetch('/api/rebuild', {method: 'POST'});
  document.getElementById('status').textContent = 'Site HTML rebuilt ✓';
  setTimeout(() => document.getElementById('status').textContent = current || 'No photo selected', 2000);
}

init();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence access log

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path in ("/", "/index.html"):
            self.send_html(HTML)

        elif path == "/api/photos":
            self.send_json(photo_list())

        elif path == "/api/metadata":
            self.send_json(load_meta())

        elif path.startswith("/photo/"):
            name = path[len("/photo/"):]
            img_path = PHOTO_DIR / name
            if not img_path.exists() or not img_path.suffix.lower() == ".jpg":
                self.send_response(404); self.end_headers(); return
            data = img_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)

        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if path == "/api/save":
            try:
                meta = json.loads(body)
                save_meta(meta)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif path == "/api/rebuild":
            try:
                result = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "update_photography.py")],
                    capture_output=True, text=True, cwd=str(REPO_ROOT)
                )
                self.send_json({"ok": True, "output": result.stdout + result.stderr})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        else:
            self.send_response(404); self.end_headers()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8090)
    args = ap.parse_args()

    server = HTTPServer(("localhost", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"Annotator running at  {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()
