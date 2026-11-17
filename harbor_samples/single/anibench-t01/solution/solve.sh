#!/bin/bash
mkdir -p /var/lib/anibench 2>/dev/null
{ [ -e /tests ] && echo 1 || echo 0; } > /var/lib/anibench/tests_visible_at_solve 2>/dev/null || true
cp /solution/ref/* /app/
