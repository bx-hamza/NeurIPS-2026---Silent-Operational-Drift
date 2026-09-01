#!/usr/bin/env bash
# make_session.sh <session_id>  -> writes runs/<sid>.arm (the arm's data-access CLI)
set -euo pipefail
SID="$1"
ROOT="${SOD_ROOT:?set SOD_ROOT to the study root directory}"
WRAP="$ROOT/sod-harness/runs/${SID}.arm"
cat > "$WRAP" <<EOF
#!/usr/bin/env bash
export SOD_TRACE_FILE="$ROOT/sod-harness/runs/${SID}.jsonl"
export SOD_MCP_LAUNCHER="$SOD_MCP_LAUNCHER"
export SOD_ORG_ID="$SOD_ORG_ID"
exec "${SOD_PYTHON:-python3}" "$ROOT/sod-harness/harness/arm_cli.py" "\$@"
EOF
chmod +x "$WRAP"
: > "$ROOT/sod-harness/runs/${SID}.jsonl"
echo "$WRAP"
