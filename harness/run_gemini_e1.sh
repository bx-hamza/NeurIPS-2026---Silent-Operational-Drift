#!/usr/bin/env bash
# Sequential E1 driver for the Gemini-Flash second family. One session at a time
# (free-tier flash is rate-limited; the runner also paces calls at MIN_GAP).
# Skips any (arm,seed) whose .status.json already exists, so it is resumable
# after a rate-limit stop. Seed-major order: finish s1 across all arms first
# (fastest path to the headline A3-vs-A4 number), then s2, s3.
set -u
cd "$(dirname "$0")/.."
PY="${SOD_PYTHON:-python3}"
GAP_BETWEEN=15   # seconds between sessions
# Overridable for other families:
#   Gemini 2.5 Pro : MODEL=gemini-2.5-pro TAG=gpro bash harness/run_gemini_e1.sh
#   DeepSeek V3    : PROVIDER=deepseek MODEL=deepseek-chat TAG=ds bash harness/run_gemini_e1.sh
PROVIDER="${PROVIDER:-gemini}"
MODEL="${MODEL:-gemini-2.5-flash}"
TAG="${TAG:-gem}"
echo "provider=$PROVIDER model=$MODEL tag=$TAG"

run() {
  local arm=$1 label=$2 seed=$3
  if [ -f "runs/${TAG}_${arm}_${label}.status.json" ]; then
    echo "skip ${arm}_${label} (already done)"; return
  fi
  echo "=== RUN ${arm}_${label} (seed ${seed}) $(date +%H:%M:%S) ==="
  $PY harness/gemini_arm.py --arm "$arm" --seed "$seed" --label "$label" \
    --provider "$PROVIDER" --model "$MODEL" --tag "$TAG" \
    > "/tmp/${TAG}_${arm}_${label}.log" 2>&1
  echo "    -> $(tail -1 /tmp/${TAG}_${arm}_${label}.log 2>/dev/null | head -c 200)"
  grep -E '"failed"|"n_ranked"|"ranked_empty"' "runs/${TAG}_${arm}_${label}.status.json" 2>/dev/null | tr -d ' \n'
  echo ""
  sleep "$GAP_BETWEEN"
}

for combo in A1:s1:1 A2:s1:1 A3:s1:1 A4:s1:1 \
             A1:s2:2 A2:s2:2 A3:s2:2 A4:s2:2 \
             A1:s3:3 A2:s3:3 A3:s3:3 A4:s3:3; do
  IFS=: read -r arm label seed <<< "$combo"
  run "$arm" "$label" "$seed"
done
echo "=== DRIVER DONE $(date +%H:%M:%S) ==="
