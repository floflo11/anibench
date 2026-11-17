"""Tests for the Harbor exporter's protocol settings (src/export_harbor.py --setting ...).

- The legacy export (no --setting) is unchanged: identical to the committed harbor/ folder.
- No setting leaks the grader, spec or masks into the agent's image (environment/ is the Docker build
  context; tests/ is only uploaded to /tests for the verifier).
- harbor_samples/<setting>/anibench-t01 is an up-to-date copy of the exporter's text files.
"""
import ast
import filecmp
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import export_harbor as ex  # noqa: E402

SETTINGS = ("single", "feedback", "agent")
SAMPLE_TASK = "anibench-t01"
ENV_ALLOWED = {"Dockerfile", "image.png", "vendor/three.module.js", "vendor/three.core.js"}
ENV_FEEDBACK = {"anibench/preview.py", "anibench/render.py", "anibench/anibench-preview"}
GRADER_ONLY = {"graders.py", "grade_app.py", "spec.json", "allowed.png", "target.png", "skull.png", "test.sh"}


def files(d):
    return {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()}


@pytest.fixture(scope="module")
def exports(tmp_path_factory):
    base = tmp_path_factory.mktemp("exports")
    out = {"legacy": ex.main(None, base / "legacy")}
    for s in SETTINGS:
        out[s] = ex.main(s, base / s)
    return out


def test_legacy_export_matches_committed_harbor(exports):
    new, old = exports["legacy"], ROOT / "harbor"
    tasks = sorted(p.name for p in old.iterdir() if p.is_dir())
    assert sorted(p.name for p in new.iterdir() if p.is_dir()) == tasks
    for t in tasks:
        fo, fn = files(old / t), files(new / t)
        # validation/*/ref/*.png is gitignored, so a clean checkout cannot rebuild the oracle layers
        ignorable = {f for f in fo if f.startswith("solution/ref/") and f.endswith(".png")}
        assert fn - fo == set(), t
        assert fo - fn <= ignorable, t
        for f in sorted(fn):
            src = {"tests/graders.py": ROOT / "src/graders.py", "tests/render.py": ROOT / "src/render.py"}.get(f, old / t / f)
            assert filecmp.cmp(new / t / f, src, shallow=False), f"{t}/{f} differs from the legacy export"


@pytest.mark.parametrize("setting", SETTINGS)
def test_environment_does_not_leak_grader(exports, setting):
    root = exports[setting]
    allowed = ENV_ALLOWED | (ENV_FEEDBACK if setting == "feedback" else set())
    tasks = [p for p in root.iterdir() if p.is_dir()]
    assert len(tasks) == 21
    for t in tasks:
        env = files(t / "environment")
        assert env == allowed, (t.name, env ^ allowed)
        assert not {Path(f).name for f in env} & (GRADER_ONLY - {"render.py"})
        # the agent's image is the original picture, byte-identical to the verifier's copy
        assert filecmp.cmp(t / "environment/image.png", t / "tests/image.png", shallow=False)
        # the Dockerfile copies only from its own build context, which holds nothing from tests/ or solution/
        docker = (t / "environment/Dockerfile").read_text()
        for src in re.findall(r"^COPY\s+(\S+)", docker, re.M):
            assert (t / "environment" / src).exists(), src
        assert "/tests" not in docker and "/solution" not in docker and ".." not in docker


def test_feedback_tool_is_renderer_not_grader(exports):
    tool = exports["feedback"] / SAMPLE_TASK / "environment/anibench"
    assert filecmp.cmp(tool / "render.py", ROOT / "src/render.py", shallow=False)
    assert filecmp.cmp(tool / "preview.py", ROOT / "harbor_template/preview.py", shallow=False)
    for f in ("render.py", "preview.py"):
        tree = ast.parse((tool / f).read_text())
        imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                    for a in getattr(n, "names", [])} | {getattr(n, "module", None) for n in ast.walk(tree)
                                                         if isinstance(n, ast.ImportFrom)}
        assert "graders" not in imported, f


def test_agent_setting_shows_agent_the_legacy_task(exports):
    for t in (p.name for p in exports["agent"].iterdir() if p.is_dir()):
        a, legacy = exports["agent"] / t, exports["legacy"] / t
        assert (a / "instruction.md").read_text() == (legacy / "instruction.md").read_text()
        for f in files(legacy / "environment"):
            assert filecmp.cmp(a / "environment" / f, legacy / "environment" / f, shallow=False)


@pytest.mark.parametrize("setting", SETTINGS)
def test_setting_metadata_and_instruction(exports, setting):
    t = exports[setting] / SAMPLE_TASK
    toml = (t / "task.toml").read_text()
    assert f'setting = "{setting}"' in toml
    assert "timeout_sec = 900" in toml  # same wall-clock budget in every setting
    instr = (t / "instruction.md").read_text()
    assert "/app/index.html" in instr
    if setting == "single":
        assert "do not run any code" in instr.lower() and "anibench-preview" not in instr
    if setting == "feedback":
        assert "`anibench-preview` **once**" in instr and "frame_5.png" in instr
    grade_app = (t / "tests/grade_app.py").read_text()
    ast.parse(grade_app)
    assert "preview_calls" in grade_app and "probe_tests_visible" in grade_app
    assert "tests_visible_at_solve" in (t / "solution/solve.sh").read_text()
    # the oracle has its reference layers even from a clean checkout
    assert {"index.html", "base.png"} <= {p.name for p in (t / "solution/ref").iterdir()}


@pytest.mark.parametrize("setting", SETTINGS)
def test_committed_samples_are_current(exports, setting):
    sample = ROOT / "harbor_samples" / setting / SAMPLE_TASK
    got = exports[setting] / SAMPLE_TASK
    committed = files(sample)
    assert committed, f"missing {sample}"
    for f in committed:
        assert filecmp.cmp(sample / f, got / f, shallow=False), f"{setting}: {f} is stale; re-run the sample copy"
