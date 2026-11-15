"""Render an animation page to frames with headless Chrome (software WebGL).

Usage from Python: frames, err = render(html_path_dir, width, height)
The directory must contain index.html; image.png and vendor/ are linked in automatically.
"""
import base64
import functools
import http.server
import io
import shutil
import socketserver
import threading
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
N_FRAMES = 25
CHROME = "/usr/bin/google-chrome"
ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
        "--use-gl=angle", "--enable-webgl", "--disable-gpu-sandbox", "--no-sandbox"]


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


_server = None


def serve(root):
    global _server
    if _server:
        return _server.server_address[1]
    handler = functools.partial(_Quiet, directory=str(root))
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    _server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    return _server.server_address[1]


def prepare(run_dir, task_dir):
    run_dir = Path(run_dir)
    shutil.copy(Path(task_dir) / "image.png", run_dir / "image.png")
    v = run_dir / "vendor"
    if not v.exists():
        v.mkdir()
        for f in ("three.module.js", "three.core.js"):
            shutil.copy(ROOT / "vendor" / f, v / f)


class Renderer:
    def __init__(self):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(executable_path=CHROME, args=ARGS, headless=True)
        self.port = serve(ROOT)

    def close(self):
        self.browser.close()
        self.pw.stop()

    def render(self, run_dir, width, height, timeout_s=15):
        """Returns (frames uint8 (N,H,W,3) or None, error string or None, console list)."""
        run_dir = Path(run_dir).resolve()
        rel = run_dir.relative_to(ROOT)
        ctx = self.browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        page = ctx.new_page()
        logs = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"[:300]))
        page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"[:300]))
        try:
            page.goto(f"http://127.0.0.1:{self.port}/{rel.as_posix()}/index.html", wait_until="load", timeout=timeout_s * 1000)
            try:
                page.wait_for_function("window.ANIM_READY === true && typeof window.setTime === 'function'", timeout=timeout_s * 1000)
            except Exception:
                return None, "RUNTIME: ANIM_READY/setTime not available within %ds" % timeout_s, logs
            js = """(n) => { const cs = [...document.querySelectorAll('canvas')];
                const c = cs.sort((a, b) => b.width * b.height - a.width * a.height)[0];
                if (!c) return null; const out = [];
                for (let i = 0; i < n; i++) { window.setTime(i * 2 / (n - 1)); out.push(c.toDataURL('image/png')); }
                return out; }"""
            urls = page.evaluate(js, N_FRAMES)
            if not urls:
                return None, "RUNTIME: no canvas on page", logs
            frames = []
            for u in urls:
                im = Image.open(io.BytesIO(base64.b64decode(u.split(",", 1)[1]))).convert("RGBA")
                bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
                bg.alpha_composite(im)
                im = bg.convert("RGB")
                if im.size != (width, height):
                    im = im.resize((width, height))
                frames.append(np.array(im))
            return np.stack(frames), None, logs
        except Exception as e:  # noqa: BLE001
            return None, f"RUNTIME: {type(e).__name__}: {str(e)[:200]}", logs
        finally:
            ctx.close()


def save_gif(frames, path, scale=0.5):
    ims = [Image.fromarray(f).resize((int(f.shape[1] * scale), int(f.shape[0] * scale)), Image.LANCZOS) for f in frames[:-1]]
    ims[0].save(path, save_all=True, append_images=ims[1:], duration=int(2000 / (len(ims))), loop=0, optimize=True)
