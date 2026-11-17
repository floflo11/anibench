"""Schema-v1 annotations: validation, exact geometry, and byte-identical regeneration of T01-T24."""
import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import annotations as A  # noqa: E402

TASK_IDS = [f"T{i:02d}" for i in range(1, 25)]
MASK_FILES = ("target.png", "allowed.png", "skull.png")


def png(path):
    return np.array(Image.open(path)) > 127


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("tasks")
    index = A.generate_tasks(ROOT / "annotations/tasks_pilot.json", out)
    return out, index


# ---- the migrated files ---------------------------------------------------------------------

@pytest.mark.parametrize("image_id", ["lineup", "toddlers"])
def test_migrated_annotation_is_valid(image_id):
    ann = A.load(ROOT / f"annotations/{image_id}.json")
    assert ann["image_id"] == image_id
    assert ann["schema_version"] == 1
    for k in A.META_KEYS:
        assert isinstance(ann["metadata"][k], str)


def test_part_masks_match_legacy_part_pngs():
    _, lib = A.library()
    legacy = json.loads((ROOT / "annotations/parts.json").read_text())
    assert set(lib) == set(legacy)
    for pid, meta in legacy.items():
        assert lib[pid]["image"] == meta["image"]
        assert lib[pid]["pivot"] == (tuple(meta["pivot"]) if meta["pivot"] else None), pid
        ref = png(ROOT / f"annotations/parts/{pid}.png")
        assert int((lib[pid]["mask"] != ref).sum()) == 0, pid
        assert int(lib[pid]["mask"].sum()) == meta["area"], pid


def test_legacy_shim_reproduces_parts():
    import parts

    built = parts.build()
    assert len(built) == 24
    for (img, pid), v in built.items():
        assert (v["mask"] == png(ROOT / f"annotations/parts/{pid}.png")).all(), pid
    # parts.save() would rewrite annotations/parts.json byte-identically (same keys, same order)
    meta = {pid: dict(image=img, pivot=list(v["pivot"]) if v["pivot"] else None, area=int(v["mask"].sum()))
            for (img, pid), v in built.items()}
    assert json.dumps(meta, indent=1) == (ROOT / "annotations/parts.json").read_text()


# ---- task regeneration ----------------------------------------------------------------------

@pytest.mark.parametrize("tid", TASK_IDS)
def test_task_masks_reproduced_exactly(generated, tid):
    out, _ = generated
    ref, new = ROOT / "tasks" / tid, out / tid
    for f in MASK_FILES:
        assert (ref / f).exists() == (new / f).exists(), f"{tid}/{f} presence differs"
        if (ref / f).exists():
            a, b = png(ref / f), png(new / f)
            assert a.shape == b.shape
            assert int((a != b).sum()) == 0, f"{tid}/{f}: {int((a != b).sum())} px differ"
            assert (ref / f).read_bytes() == (new / f).read_bytes(), f"{tid}/{f} not byte-identical"
    assert (ref / "image.png").read_bytes() == (new / "image.png").read_bytes()
    assert (ref / "prompt.md").read_text() == (new / "prompt.md").read_text()


@pytest.mark.parametrize("tid", TASK_IDS)
def test_task_spec_reproduced(generated, tid):
    out, _ = generated
    ref = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
    new = json.loads((out / tid / "spec.json").read_text())
    # src/admission.py later narrows "graders" and keeps the generated list in "graders_all"
    if "graders_all" in ref:
        ref["graders"] = ref.pop("graders_all")
    assert new == ref


def test_task_index_reproduced(generated):
    out, index = generated
    assert (out / "index.json").read_text() == (ROOT / "tasks/index.json").read_text()
    assert [s["id"] for s in index] == TASK_IDS


# ---- geometry -------------------------------------------------------------------------------

def test_fill_uses_pixel_centres():
    # square with corners on pixel corners covers exactly pixels 2..4 x 1..2
    m = A.fill([[[1.5, 0.5], [4.5, 0.5], [4.5, 2.5], [1.5, 2.5]]], (5, 7))
    exp = np.zeros((5, 7), bool)
    exp[1:3, 2:5] = True
    assert (m == exp).all()
    # polygons of a part are unioned, not xor-ed
    two = A.fill([[[0, 0], [4, 0], [4, 4], [0, 4]], [[2, 2], [6, 2], [6, 6], [2, 6]]], (8, 8))
    assert two[3, 3] and two[1, 1] and two[5, 5]


def test_trace_fill_round_trip():
    rng = np.random.default_rng(0)
    for i in range(100):
        m = ndimage.binary_fill_holes(rng.random((18, 23)) < rng.uniform(0.2, 0.7))
        assert (A.fill(A.trace(m), m.shape) == m).all(), i


def test_trace_rejects_holes():
    m = np.zeros((10, 10), bool)
    m[2:8, 2:8] = True
    m[4:6, 4:6] = False
    with pytest.raises(ValueError, match="hole"):
        A.trace(m)


# ---- validation -----------------------------------------------------------------------------

def minimal():
    return {
        "schema_version": 1,
        "image_id": "demo",
        "image": {"path": "images/demo.png", "width": 40, "height": 30},
        "metadata": {"style": "flat", "subject": "test", "source": "unit test", "license": "CC0"},
        "parts": [
            {"name": "body", "polygons": [[[1, 1], [30, 1], [30, 25], [1, 25]]], "pivot": None, "parent": None},
            {"name": "hand", "polygons": [[[5, 5], [10, 5], [10, 10]]], "pivot": [6, 9], "parent": "body",
             "exclude": ["hat"]},
            {"name": "hat", "polygons": [[[8, 2], [14, 2], [14, 6]]], "pivot": [9, 6], "parent": "body"},
        ],
        "masks": [{"name": "skull", "role": "keep", "part": "hat", "polygons": [[[9, 4], [12, 4], [12, 6]]]}],
    }


def test_minimal_is_valid():
    A.validate(minimal())


def broken(fn):
    a = minimal()
    fn(a)
    return a


@pytest.mark.parametrize("mutate,msg", [
    (lambda a: a["parts"][1].pop("pivot"), "missing 'pivot'"),
    (lambda a: a["parts"][1].__setitem__("polygons", [[[5, 5], [10, 5]]]), "at least 3"),
    (lambda a: a["parts"][1].__setitem__("polygons", []), "non-empty list"),
    (lambda a: a["parts"][1].__setitem__("pivot", [6]), "pivot"),
    (lambda a: a["parts"][1].__setitem__("parent", "nope"), "parent 'nope'"),
    (lambda a: a["parts"][0].__setitem__("parent", "hand"), "cycle"),
    (lambda a: a["parts"][1].pop("parent"), "missing 'parent'"),
    (lambda a: a["parts"][1].__setitem__("exclude", ["ghost"]), "exclude 'ghost'"),
    (lambda a: a["parts"][1].__setitem__("exclude", ["hand"]), "itself"),
    (lambda a: a["parts"][2].__setitem__("name", "hand"), "duplicate"),
    (lambda a: a["parts"][1].__setitem__("clip", "maybe"), "clip"),
    (lambda a: a.__setitem__("schema_version", 2), "schema_version"),
    (lambda a: a["image"].pop("width"), "width"),
    (lambda a: a["metadata"].pop("license"), "license"),
    (lambda a: a["masks"][0].__setitem__("part", "ghost"), "'part'"),
    (lambda a: a["masks"][0].__setitem__("role", "other"), "role"),
])
def test_validation_errors(mutate, msg):
    with pytest.raises(A.AnnotationError, match=msg):
        A.validate(broken(mutate))


def test_load_reports_file_name(tmp_path):
    a = broken(lambda a: a["parts"][1].pop("pivot"))
    p = tmp_path / "demo.json"
    p.write_text(json.dumps(a))
    with pytest.raises(A.AnnotationError, match=r"demo\.json: part 'hand': missing 'pivot'"):
        A.load(p)


def test_mask_pipeline_clip_outline_exclude():
    a = minimal()
    fg = np.zeros((30, 40), bool)
    fg[2:24, 2:29] = True
    ms = A.masks(copy.deepcopy(a), fg=fg)
    assert not (ms["body"] & ~fg).any()                        # clipped to the foreground
    hat = A.fill(a["parts"][2]["polygons"], fg.shape)
    assert not (ms["hand"] & ndimage.binary_dilation(hat, iterations=4)).any()  # excluded + margin
    a["parts"][1]["exclude"] = []
    grown = A.masks(a, fg=fg)["hand"]
    assert grown.sum() > ms["hand"].sum()
    assert ms["skull"].sum() > 0


def test_migration_script_reproduces_committed_json():
    sys.path.insert(0, str(ROOT / "scripts"))
    import migrate_legacy_parts as M

    # parts corrected by hand after the migration (grader v3; see results/grader_v3.md): T07 earrings + chain,
    # B2_head sleeve sliver, A2_forearm pigtail strip, A3_head fleck. Every other part is still the migration's.
    edited = {"A4_earringL", "A4_earringR", "B2_head", "A2_forearm", "A3_head"}
    for name, ann in M.migrate().items():  # migrate() asserts every mask equals the legacy colour-rule mask
        cur = json.loads((ROOT / f"annotations/{name}.json").read_text())
        assert {k: v for k, v in cur.items() if k != "parts"} == {k: v for k, v in ann.items() if k != "parts"}
        assert [p["name"] for p in cur["parts"]] == [p["name"] for p in ann["parts"]]
        for pc, pm in zip(cur["parts"], ann["parts"]):
            if pc["name"] not in edited:
                assert pc == pm, pc["name"]


def test_preview_writes_overlay(tmp_path):
    out = A.preview(A.load(ROOT / "annotations/lineup.json"), tmp_path / "p.png")
    assert Image.open(out).size == (1200, 600)
