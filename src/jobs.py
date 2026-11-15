"""Make the job list the browser runner executes, and ingest the results it returns.

python3 src/jobs.py make <name> <models comma> <tasks comma|all> <tries>
python3 src/jobs.py ingest <results_json_file>
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "sonnet": "anthropic/claude-sonnet-5.5",
    "sol": "openai/gpt-6.1-sol",
    "qwen": "qwen/qwen3.8-27b",
    "nemotron": "nvidia/nemotron-3.5-super-vl:free",
    "gemma": "google/gemma-4-31b-it:free",
    "gemini4": "google/gemini-4-carbon",
    "grok": "x-ai/grok-4.7",
    "kimi": "moonshotai/kimi-k3.1-pro",
    "deepseek": "deepseek/deepseek-v4-flash-vision-exp",
}


def make(name, models, tasks, tries):
    idx = json.loads((ROOT / "tasks/index.json").read_text())
    ids = [s["id"] for s in idx] if tasks == ["all"] else tasks
    jobs = []
    for m in models:
        for tid in ids:
            spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
            prompt = (ROOT / "tasks" / tid / "prompt.md").read_text()
            for k in range(1, tries + 1):
                jobs.append(dict(id=f"{m}__{tid}__{k}", model=MODELS[m], task=tid, try_=k,
                                 image=spec["image"], prompt=prompt))
    out = ROOT / "runs/jobs" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(jobs))
    print(out, len(jobs))


HTML_RE = re.compile(r"```(?:html)?\s*\n(.*?)```", re.S | re.I)


def extract_html(text):
    if not text:
        return None
    blocks = HTML_RE.findall(text)
    if blocks:
        return max(blocks, key=len)
    i = text.lower().find("<!doctype")
    if i < 0:
        i = text.lower().find("<html")
    return text[i:] if i >= 0 else None


def ingest(path):
    raw = json.loads(Path(path).read_text())
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and "type" in raw[0]:
        # saved browser tool result: [{type:'text', text:'"<json string>"\n\n(captured ...)'}]
        txt = raw[0]["text"].lstrip()
        val, _ = json.JSONDecoder().raw_decode(txt)
        raw = json.loads(val) if isinstance(val, str) else val
    results = raw["results"] if isinstance(raw, dict) and "results" in raw else raw
    n = 0
    for r in results.values() if isinstance(results, dict) else results:
        m, tid, k = r["id"].split("__")
        d = ROOT / "runs" / m / tid / k
        d.mkdir(parents=True, exist_ok=True)
        stage = r.get("stage", "first")
        (d / f"response_{stage}.txt").write_text(r.get("content") or "")
        html = extract_html(r.get("content"))
        meta = {k2: v for k2, v in r.items() if k2 != "content"}
        meta["has_html"] = html is not None
        (d / f"meta_{stage}.json").write_text(json.dumps(meta, indent=1))
        if html:
            (d / f"index_{stage}.html").write_text(html)
        n += 1
    print("ingested", n)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "make":
        make(sys.argv[2], sys.argv[3].split(","), sys.argv[4].split(","), int(sys.argv[5]))
    elif cmd == "ingest":
        ingest(sys.argv[2])
