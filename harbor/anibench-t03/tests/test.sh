#!/bin/bash
set -u
mkdir -p /logs/verifier
cd /tests
python3 /tests/grade_app.py /app /tests > /logs/verifier/grade_log.txt 2>&1
if [ ! -f /logs/verifier/reward.txt ]; then echo 0 > /logs/verifier/reward.txt; fi
cat /logs/verifier/grade_log.txt | tail -20
