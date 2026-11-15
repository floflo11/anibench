"""Build the demo video (MP4, 1280x720) from title cards, failure clips with check overlays and charts.

python3 src/make_video.py  -> results/demo.mp4
Clip list comes from results/demo_clips.json: [{"run": "nemotron/T01/1", "stage": "first", "caption": "..."}]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageSequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
W, H, FPS = 1280, 720, 24
BG = (250, 249, 246)
INK = (28, 28, 30)
QUIET = (100, 100, 108)
ACCENT = (59, 111, 216)
BAD = (200, 60, 50)
GOOD = (40, 140, 80)
GNAME = {"G1": "Isolation", "G2": "Integrity", "G3": "Area", "G4": "Motion", "G5": "Pivot", "G6": "Loop"}


def font(size, bold=False):
    for p in (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold else []) + [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def card(title, sub="", sub2=""):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((90, 250), title, font=font(54, True), fill=INK)
    if sub:
        d.text((92, 340), sub, font=font(28), fill=QUIET)
    if sub2:
        d.text((92, 385), sub2, font=font(28), fill=QUIET)
    d.rectangle([90, 230, 170, 236], fill=ACCENT)
    return im


def fit(im, box_w, box_h):
    r = min(box_w / im.width, box_h / im.height)
    return im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)


def clip_frames(run, stage, caption, seconds=6):
    d = ROOT / "runs" / run
    gif = Image.open(d / f"anim_{stage}.gif")
    src = [f.convert("RGB") for f in ImageSequence.Iterator(gif)]
    g = json.loads((d / f"grade_{stage}.json").read_text())
    orig = Image.open(ROOT / "tasks" / g["task"] / "image.png").convert("RGB")
    spec = json.loads((ROOT / "tasks" / g["task"] / "spec.json").read_text())
    out = []
    n = seconds * FPS
    for i in range(n):
        im = Image.new("RGB", (W, H), BG)
        dr = ImageDraw.Draw(im)
        dr.text((40, 26), caption, font=font(30, True), fill=INK)
        dr.text((40, 68), f"{g['model']} · {g['task']}: “{spec['instruction']}”"[:110], font=font(18), fill=QUIET)
        # left: original (small), right: model output (large)
        o = fit(orig, 380, 300)
        im.paste(o, (40, 140))
        dr.text((40, 112), "Original", font=font(18, True), fill=QUIET)
        f = fit(src[int(i * len(src) / FPS / 2) % len(src)], 800, 470)
        im.paste(f, (450, 140))
        dr.text((450, 112), "Model's animation", font=font(18, True), fill=QUIET)
        # checks panel
        y = 470
        for k in ("G1", "G2", "G3", "G4", "G5", "G6"):
            if "grades" in g and k in g["grades"]:
                ok = g["grades"][k]["ok"]
                dr.rounded_rectangle([40, y, 400, y + 30], 6, fill=(232, 244, 236) if ok else (250, 230, 228))
                dr.text((52, y + 5), f"{k} {GNAME[k]}", font=font(18, True), fill=INK)
                dr.text((330, y + 5), "pass" if ok else "FAIL", font=font(18, True), fill=GOOD if ok else BAD)
                y += 36
        out.append(im)
    return out


def still(path, title, seconds=5):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((40, 26), title, font=font(32, True), fill=INK)
    c = fit(Image.open(path).convert("RGB"), 1180, 600)
    im.paste(c, ((W - c.width) // 2, 100))
    return [im] * (seconds * FPS)


def main():
    plan = json.loads((ROOT / "results/demo_clips.json").read_text())
    frames = []
    frames += [card("anibench", "Can frontier models animate one part of a picture", "without breaking everything else?")] * (4 * FPS)
    frames += [card("The task", "Image + instruction (“wave his raised hand from the wrist”)", "→ model writes three.js → we render 25 frames and run 6 pixel checks")] * (5 * FPS)
    for c in plan["clips"]:
        frames += clip_frames(c["run"], c.get("stage", "first"), c["caption"], c.get("seconds", 6))
    for s in plan.get("stills", []):
        frames += still(ROOT / s["path"], s["title"], s.get("seconds", 5))
    frames += [card(plan.get("end_title", "No model judge. Just pixels."), plan.get("end_sub", ""), plan.get("end_sub2", ""))] * (4 * FPS)
    tmp = Path(tempfile.mkdtemp())
    for i, f in enumerate(frames):
        f.save(tmp / f"f{i:05d}.png")
    out = ROOT / "results/demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "f%05d.png"),
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-crf", "20", str(out)], check=True)
    print(out, len(frames) / FPS, "s")


if __name__ == "__main__":
    main()
