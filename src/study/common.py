"""Shared vocabulary for the human study: defect codes, their wording, and the check each one maps to.

tools/rater.html and src/study/judge_schema.json carry the same codes; tests/test_study_*.py check that
all three agree.
"""
CHECKS = ["G1", "G2", "G2b", "G3", "G4", "G5", "G6"]

# code, label shown to raters (and to judges), checks the defect corresponds to.
DEFECTS = [
    ("outside_moved", "Something outside the part moved", ["G1"]),
    ("tore_split", "The part tore, split or left a piece behind", ["G2", "G2b"]),
    ("size_shape", "The part changed size or shape", ["G3"]),
    ("barely_moves", "The part barely moves (or does not move)", ["G4"]),
    ("wrong_pivot", "The part rotates around the wrong point", ["G5"]),
    ("loop_jump", "Jump at the loop, or the first frame differs from the image", ["G6"]),
    ("other", "Other (describe)", []),
]
DEFECT_CODES = [d[0] for d in DEFECTS]
DEFECT_LABEL = {d[0]: d[1] for d in DEFECTS}
DEFECT_CHECKS = {d[0]: d[2] for d in DEFECTS if d[2]}

QUESTION = "Did the animation do what was asked without breaking anything else?"

MANIFEST_SCHEMA = "anibench-study-manifest-v1"
KEY_SCHEMA = "anibench-study-key-v1"
RATING_SCHEMA = "anibench-rating-v1"
