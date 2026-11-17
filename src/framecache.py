"""Content-addressed cache of rendered frames, so grader changes can be re-scored without Chrome.

A page directory is keyed by the bytes of every file in it (index.html, layer PNGs, ...; vendor/ and the
copied image.png excluded), the task image and the canvas size. Frames are stored as the uint8 difference
from the task image (compresses ~80x, since most pixels never change), under scratch/frames/ (gitignored).
Render errors are cached too. Rendering is deterministic (pinned Chrome, software WebGL), so a cached
result is the same as a fresh render.

    from framecache import CachedRenderer
    R = CachedRenderer()           # Chrome starts only on the first cache miss
    frames, err, logs = R.render(page_dir, task_dir, width, height)
    R.close()
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("ANIBENCH_FRAME_CACHE", ROOT / "scratch" / "frames"))
SKIP = {"vendor", "image.png", "anim.gif"}


def page_key(page_dir, task_dir, width, height):
    h = hashlib.sha1(f"{width}x{height}".encode())
    page_dir = Path(page_dir)
    for p in sorted(page_dir.rglob("*")):
        rel = p.relative_to(page_dir)
        if rel.parts[0] in SKIP or not p.is_file():
            continue
        h.update(str(rel).encode())
        h.update(p.read_bytes())
    h.update((Path(task_dir) / "image.png").read_bytes())
    return h.hexdigest()


def task_image(task_dir):
    return np.array(Image.open(Path(task_dir) / "image.png").convert("RGB"))


def load(key, task_dir):
    p = CACHE / f"{key}.npz"
    if p.exists():
        d = np.load(p)
        return (d["diff"] + task_image(task_dir)[None]).astype(np.uint8), None, []
    e = CACHE / f"{key}.err.json"
    if e.exists():
        x = json.loads(e.read_text())
        return None, x["error"], x["logs"]
    return "miss"


def store(key, task_dir, frames, err, logs):
    CACHE.mkdir(parents=True, exist_ok=True)
    if frames is None:
        (CACHE / f"{key}.err.json").write_text(json.dumps(dict(error=err, logs=logs)))
        return
    tmp = CACHE / f"{key}.tmp.npz"
    np.savez_compressed(tmp, diff=(frames - task_image(task_dir)[None]).astype(np.uint8))
    tmp.rename(CACHE / f"{key}.npz")


class CachedRenderer:
    def __init__(self, use_cache=True):
        self.R = None
        self.use_cache = use_cache
        self.hits = self.misses = 0

    def render(self, page_dir, task_dir, width, height):
        from render import prepare
        prepare(page_dir, task_dir)
        key = page_key(page_dir, task_dir, width, height)
        if self.use_cache:
            got = load(key, task_dir)
            if got != "miss":
                self.hits += 1
                return got
        self.misses += 1
        if self.R is None:
            from render import Renderer
            self.R = Renderer()
        fr, err, logs = self.R.render(page_dir, width, height)
        store(key, task_dir, fr, err, logs)
        return fr, err, logs

    def close(self):
        if self.R is not None:
            self.R.close()
            self.R = None
