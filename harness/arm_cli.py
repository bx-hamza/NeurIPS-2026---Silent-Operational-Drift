#!/usr/bin/env python3
"""
Logging data-access CLI for arm sessions. The arm sub-agent reaches the graph
ONLY through this tool, so every query string is captured verbatim as the gateway
received it (CLAUDE.md #1: executed_binding comes only from query strings the
gateway received — never reconstructed from prose).

Each invocation appends one trace record to $SOD_TRACE_FILE before returning
results. Turn numbers come from $SOD_TRACE_FILE's current line count.

Subcommands (what an arm is told to use):
  cypher "<CYPHER>"                 A2/A3/A4 raw read query via the gateway
  tool <mcp_tool> '<json-args>'     A3/A4 structured MCP tool call
  rank  '["GENE1","GENE2",...]'     record the arm's FINAL ranking
  say   "<free text>"               record a narration line (what it claims it did)

Env:
  SOD_TRACE_FILE  path to the session's .jsonl trace (required)
  SOD_ORG_ID      org id for the gateway (default: study org)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.gateway import execute_query, STUDY_ORG_ID  # noqa: E402

TRACE = os.environ.get("SOD_TRACE_FILE")
ORG = os.environ.get("SOD_ORG_ID", STUDY_ORG_ID)

# MCP tools an arm may call. Driven through the same stdio launcher the harness
# uses; args are logged verbatim as raw_query so structured calls are auditable.
MCP_LAUNCHER = os.environ.get("SOD_MCP_LAUNCHER", "")  # MCP stdio launcher


def _turn() -> int:
    if not TRACE or not Path(TRACE).exists():
        return 1
    with open(TRACE) as fh:
        return sum(1 for _ in fh) + 1


def _log(rec: dict) -> None:
    if not TRACE:
        print("ERROR: SOD_TRACE_FILE not set", file=sys.stderr)
        sys.exit(2)
    rec = {"turn": _turn(), **rec}
    Path(TRACE).parent.mkdir(parents=True, exist_ok=True)
    with open(TRACE, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def do_cypher(q: str) -> None:
    _log({"kind": "tool_call", "tool": "query", "raw_query": q})
    try:
        rows = execute_query(q, org_id=ORG)
        out = json.dumps(rows, default=str)
        # Never emit invalid (mid-)truncated JSON. If the result is very large,
        # return a valid envelope with a head + row count so the arm knows to
        # aggregate server-side rather than parsing a broken string.
        if len(out) > 60000:
            head = json.dumps(rows[:200], default=str)
            print(json.dumps({"_truncated": True, "n_rows": len(rows),
                              "note": "result large; showing first 200 rows — "
                                      "aggregate/score in Cypher instead of pulling raw",
                              "rows_head": json.loads(head)}, default=str))
        else:
            print(out)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": str(e)}))


def do_tool(name: str, args_json: str) -> None:
    # raw_query = the serialised structured args, so extract.STRUCTURED_ADAPTERS
    # can parse it; NEVER guess what the tool ran.
    _log({"kind": "tool_call", "tool": name, "raw_query": args_json,
          "input": json.loads(args_json) if args_json else {}})
    from harness.mcp_client import McpStdioClient
    c = McpStdioClient(launcher=MCP_LAUNCHER, timeout=120)
    try:
        c.initialize()
        r = c.call_tool(name, json.loads(args_json) if args_json else {})
        try:
            print(r["result"]["content"][0]["text"][:8000])
        except Exception:
            print(json.dumps(r.get("result", r))[:8000])
    finally:
        c.close()


def do_rank(entities_json: str) -> None:
    _log({"kind": "final_ranking", "entities": json.loads(entities_json)})
    print("recorded final ranking")


def do_say(text: str) -> None:
    _log({"kind": "text", "content": text})
    print("recorded")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "cypher":
        do_cypher(sys.argv[2])
    elif cmd == "tool":
        do_tool(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "{}")
    elif cmd == "rank":
        do_rank(sys.argv[2])
    elif cmd == "say":
        do_say(sys.argv[2])
    else:
        print(f"unknown subcommand {cmd!r}")
        sys.exit(1)
