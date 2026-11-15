#!/bin/bash
set -u
mkdir -p /logs/verifier
LOG=/logs/verifier/grade_log.txt
{ echo "PATH=$PATH"; which -a python3 2>/dev/null; } > "$LOG"
[ -d /ms-playwright ] && export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
PY=""
for c in /usr/bin/python3 /usr/local/bin/python3 $(which -a python3 2>/dev/null); do
  if [ -x "$c" ] && "$c" -c "import playwright, numpy, PIL, scipy" 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  PY=/usr/bin/python3; [ -x "$PY" ] || PY=$(command -v python3)
  echo "installing grader packages into $PY" >> "$LOG"
  "$PY" -m pip install -q playwright==1.49.0 numpy pillow scipy >> "$LOG" 2>&1 \
    || "$PY" -m pip install -q --break-system-packages playwright==1.49.0 numpy pillow scipy >> "$LOG" 2>&1
fi
echo "using $PY" >> "$LOG"
"$PY" -c "from playwright.sync_api import sync_playwright as s; p=s().start(); b=p.chromium.launch(); b.close(); p.stop()" >> "$LOG" 2>&1 \
  || "$PY" -m playwright install chromium >> "$LOG" 2>&1
cd /tests
"$PY" /tests/grade_app.py /app /tests >> "$LOG" 2>&1
if [ ! -f /logs/verifier/reward.txt ]; then echo 0 > /logs/verifier/reward.txt; fi
tail -40 "$LOG"
