"""calibrate_server.py — local server for the semantic-layer calibration UI.

A static file:// page can't write to the project (browser sandbox), so Accept
there just downloads to ~/Downloads. This tiny localhost server fixes that:
it serves the calibration page over http and accepts the calibrated JSON on a
POST /save endpoint, writing it straight into the project —
  data/05_normalized/figure_calibrated/<stem>.json
— so accepted figures land in the repo, not Downloads. Pure stdlib, no deps,
binds to 127.0.0.1 only (not exposed to the network).

It also drives a WORKLIST: point it at a set of figures (each with its
.lfline.json) and it serves them one at a time; Accept saves and auto-advances
to the next un-done figure. This is how the human gate walks the ~20-40
triage-selected figures in one sitting.

  # one figure:
  venv/bin/python scripts/extraction/calibrate_server.py \
      --image figures/_calib_test/mcat_fig06_panelA.png \
      --lfline outputs/charts/mcat_fig06_panelA.lfline.json
  # a worklist (JSON list of {image, lfline[, panel]}):
  venv/bin/python scripts/extraction/calibrate_server.py --worklist outputs/reports/calib_worklist.json

then open http://127.0.0.1:8137/ . Ctrl-C to stop. Resumable: figures whose
calibrated JSON already exists are skipped (status shown in the worklist).
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibrate_page import build_html  # noqa: E402

SAVE_DIR = ROOT / "data" / "05_normalized" / "figure_calibrated"


def load_worklist(args) -> list[dict]:
    if args.worklist:
        items = json.loads(Path(args.worklist).read_text())
        return [{"image": it["image"], "lfline": it["lfline"], "panel": it.get("panel", 0)}
                for it in items]
    return [{"image": args.image, "lfline": args.lfline, "panel": args.panel}]


def make_handler(worklist: list[dict]):
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    def stem_of(item) -> str:
        return Path(item["image"]).stem

    def is_done(item) -> bool:
        return (SAVE_DIR / f"{stem_of(item)}.json").exists()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                # show the first not-yet-done figure (or fall back to first)
                idx = next((i for i, it in enumerate(worklist) if not is_done(it)), None)
                if idx is None:
                    done = len(worklist)
                    self._send(200, f"<h2 style='font:16px sans-serif'>All {done} figures calibrated ✓</h2>"
                                    f"<p>Saved under data/05_normalized/figure_calibrated/. You can stop the server (Ctrl-C).</p>",
                               "text/html")
                    return
                self._serve_figure(idx)
            elif u.path == "/fig":
                idx = int(parse_qs(u.query).get("i", ["0"])[0])
                self._serve_figure(idx)
            elif u.path == "/status":
                self._send(200, json.dumps({
                    "total": len(worklist),
                    "done": sum(is_done(it) for it in worklist),
                    "items": [{"stem": stem_of(it), "done": is_done(it)} for it in worklist]}))
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def _serve_figure(self, idx):
            it = worklist[idx]
            try:
                html, stem, nser, npts = build_html(Path(it["image"]), Path(it["lfline"]), it.get("panel", 0))
            except Exception as e:
                self._send(500, json.dumps({"error": f"build failed for {it['image']}: {e}"}))
                return
            # progress banner + the next-target hint for auto-advance after save
            nxt = next((j for j in range(idx + 1, len(worklist)) if not is_done(worklist[j])), None)
            inject = (f"<script>window.__NEXT__={'/fig?i='+str(nxt) if nxt is not None else 'null'};"
                      f"window.__PROG__={{idx:{idx+1},total:{len(worklist)}}};</script>")
            html = html.replace("</body>", inject + "</body>")
            self._send(200, html, "text/html")

        def do_POST(self):
            if urlparse(self.path).path != "/save":
                self._send(404, json.dumps({"error": "not found"}))
                return
            n = int(self.headers.get("Content-Length", 0))
            try:
                obj = json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception as e:
                self._send(400, json.dumps({"ok": False, "error": f"bad json: {e}"}))
                return
            stem = Path(obj.get("image", "calibrated")).stem or "calibrated"
            path = SAVE_DIR / f"{stem}.json"
            path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            # find next undone figure to advance to
            nxt = next((j for j, it in enumerate(worklist) if not is_done(it)), None)
            rel = path.relative_to(ROOT)
            print(f"  saved {obj.get('status','?'):8} → {rel}  ({len(obj.get('series',[]))} series)")
            self._send(200, json.dumps({"ok": True, "path": str(rel),
                                        "next": (f"/fig?i={nxt}" if nxt is not None else None)}))

    return H


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image"); ap.add_argument("--lfline"); ap.add_argument("--panel", type=int, default=0)
    ap.add_argument("--worklist", help="JSON list of {image, lfline[, panel]}")
    ap.add_argument("--port", type=int, default=8137)
    args = ap.parse_args()
    if not args.worklist and not (args.image and args.lfline):
        raise SystemExit("pass --worklist, or --image + --lfline")

    worklist = load_worklist(args)
    done = sum((SAVE_DIR / f"{Path(it['image']).stem}.json").exists() for it in worklist)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(worklist))
    print(f"calibrate-server · {len(worklist)} figure(s), {done} already done")
    print(f"  saving to: {SAVE_DIR.relative_to(ROOT)}/")
    print(f"  open:      http://127.0.0.1:{args.port}/    (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
