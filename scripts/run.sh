#!/bin/bash
# anibench on Valkyrie. Run from the repo root on your Mac (needs valkyrie login + secrets).
#
#   scripts/run.sh push      upload harbor/ as dataset anibench/core@v1
#   scripts/run.sh oracle    reference solutions; must score 1 on every task
#   scripts/run.sh smoke     Sonnet on T01 only (checks the image builds and the verifier runs)
#   scripts/run.sh checks    push + oracle + smoke, one after another
#   scripts/run.sh full      Sonnet 5.5 and GPT-6.1 Sol on all 21 scored tasks, $TRIES times each
#   scripts/run.sh others    OpenRouter models via the Terminus 2 agent (needs secret openrouter-api-key)
#
# Every run waits for completion (--connect) and saves results + outputs under out/<label>-<time>/.
# Model names: check with `valkyrie run start --help` or staff; override CLAUDE_MODEL / OPENAI_MODEL.
set -euo pipefail

ORG="${ORG:-hackathon-arena-horses-10639006c9}"
BENCH="${BENCH:-anibench}"
TAG="${TAG:-v1}"
CONC="${CONC:-8}"
TRIES="${TRIES:-3}"
CLAUDE_MODEL="${CLAUDE_MODEL:-anthropic/claude-sonnet-5-5}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-6.1-sol}"
CLAUDE_AGENT="${CLAUDE_AGENT:-claude_code-v1.0.0}"
OPENAI_AGENT="${OPENAI_AGENT:-codex-v1.0.0}"
OTHER_AGENT="${OTHER_AGENT:-terminus2}"
OTHER_MODELS="${OTHER_MODELS:-openrouter/google/gemini-4-carbon openrouter/x-ai/grok-4.7 openrouter/moonshotai/kimi-k3.1-pro openrouter/qwen/qwen3.8-27b}"
LOG="${LOG:-runs.log}"

start() {  # start <label> <agent> <model|-> <task-ids|all> <secret flags...>
  local label="$1" agent="$2" model="$3" ids="$4"; shift 4
  local sel=() mod=()
  [ "$ids" != "all" ] && sel=(--task-ids "$ids")
  [ "$model" != "-" ] && mod=(--model "$model")
  echo ">> $label"
  out=$(valkyrie run start --agent "$agent" --dataset "$BENCH/core@$TAG" \
        ${mod[@]+"${mod[@]}"} --provider modal --concurrency "$CONC" ${sel[@]+"${sel[@]}"} "$@" \
        --connect 2>&1 | tee /dev/stderr) || true
  rid=$(echo "$out" | grep -Eo '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1 || true)
  echo "$(date -u +%FT%TZ) $rid $label $agent $model" >> "$LOG"
  if [ -n "$rid" ]; then
    local dir="out/$label-$(date -u +%H%M%S)"
    mkdir -p "$dir"
    echo "$out" > "$dir/console.txt"
    valkyrie run results "$rid" --path "$dir/results.json" || echo "!! results download failed for $rid"
    valkyrie run outputs "$rid" --output-dir "$dir/outputs" || echo "!! outputs download failed for $rid"
    echo ">> saved $label ($rid) to $dir"
  else
    echo "!! no run id for $label"
  fi
}
claude() { start "$1" "$CLAUDE_AGENT" "$CLAUDE_MODEL" "$2" -s ANTHROPIC_API_KEY anthropic-api-key; }
openai() { start "$1" "$OPENAI_AGENT" "$OPENAI_MODEL" "$2" -s OPENAI_API_KEY openai-api-key; }

case "${1:-}" in
  push)   valkyrie org use "$ORG"
          valkyrie dataset push "$BENCH/core" harbor --tag "$TAG" ;;
  oracle) start "oracle" oracle - all ;;
  smoke)  claude "smoke-sonnet" anibench-t01 ;;
  checks) "$0" push && "$0" oracle && "$0" smoke && echo "checks finished" ;;
  full)   for i in $(seq 1 "$TRIES"); do
            claude "full-sonnet-try$i" all
            openai "full-sol-try$i" all
          done
          echo "full finished" ;;
  others) for m in $OTHER_MODELS; do
            start "other-$(basename "$m")" "$OTHER_AGENT" "$m" all -s OPENROUTER_API_KEY openrouter-api-key -k max_turns 40
          done
          echo "others finished" ;;
  *)      sed -n '2,14p' "$0"; exit 1 ;;
esac
