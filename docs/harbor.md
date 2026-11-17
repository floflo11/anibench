# anibench — Harbor tasks

21 scored tasks. Upload with `scripts/run.sh push` from the repo root.

Each task: the agent writes `/app/index.html`; `tests/test.sh` renders it in headless Chromium and runs the six checks; reward 1 = all applicable checks pass. `solution/solve.sh` installs the reference animation (oracle).

The evaluation protocol (settings `single`, `feedback`, `agent`, each its own dataset `anibench/<setting>`, exported with `python3 src/export_harbor.py --setting <name>`) is in `docs/protocol.md`.
