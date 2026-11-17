# Harbor export samples, one per protocol setting

Text files of `anibench-t01` as exported by `python3 src/export_harbor.py --setting <single|feedback|agent>`,
for review. Binaries and copies of repo files (image.png, vendor/, masks, spec.json, graders.py, render.py,
preview.py, reference layers) are left out. Full exports go to `build/harbor-<setting>/` (gitignored).
`tests/test_export.py` fails if these samples drift from the exporter. To refresh them, export to a scratch
folder and copy the same files back. See `docs/protocol.md`.
