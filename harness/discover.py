#!/usr/bin/env python3
"""
Probe the platform gateway and report which capabilities the SOD study needs.

Run this FIRST, on the machine where the gateway is running:

    python3 discover.py --base http://the gateway endpoint > discovery.json

It is read-only: every request is GET or an OPTIONS/HEAD preflight, and the
only POSTs are to endpoints whose names indicate introspection. It never
mutates the graph.

Output is a capability report keyed by the six requirements in the protocol.
Paste discovery.json back and the harness config can be filled in exactly.
"""

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

import requests

TIMEOUT = 10

# Candidate paths per capability. The probe walks these in order and records
# every one that responds, so we learn the real surface rather than assuming.
CANDIDATES: Dict[str, List[str]] = {
    "introspection": [
        "/", "/health", "/healthz", "/version", "/openapi.json", "/docs",
        "/swagger.json", "/.well-known/openapi", "/api", "/api/v1",
    ],
    "mcp": [
        "/mcp", "/sse", "/api/mcp", "/v1/mcp", "/mcp/sse", "/messages",
    ],
    "query_execution": [
        "/query", "/cypher", "/api/query", "/api/cypher", "/v1/query",
        "/graph/query", "/db/query", "/execute",
    ],
    "framework_read": [
        "/reasoning-systems", "/frameworks", "/graph-models", "/api/graph-models",
        "/reasoning", "/decision-modules", "/modules", "/api/reasoning-systems",
    ],
    "snapshot": [
        "/snapshots", "/api/snapshots", "/snapshot", "/reports",
        "/graph/snapshots", "/versions",
    ],
    "mutation": [
        "/mutate", "/api/mutate", "/write", "/graph/write", "/edges", "/ingest",
    ],
}

# Endpoints where a POST is safe because the payload is a read-only query.
# Nothing here writes.
READ_ONLY_POST_PROBES = {
    "query_execution": {"query": "RETURN 1 AS probe", "cypher": "RETURN 1 AS probe"},
}


def probe(base: str, path: str, method: str = "GET",
          payload: Optional[dict] = None) -> Dict[str, Any]:
    url = base.rstrip("/") + path
    rec: Dict[str, Any] = {"path": path, "method": method}
    try:
        if method == "GET":
            r = requests.get(url, timeout=TIMEOUT)
        elif method == "POST":
            r = requests.post(url, json=payload, timeout=TIMEOUT)
        else:
            r = requests.options(url, timeout=TIMEOUT)
        rec["status"] = r.status_code
        rec["content_type"] = r.headers.get("content-type", "")
        allow = r.headers.get("allow") or r.headers.get("access-control-allow-methods")
        if allow:
            rec["allow"] = allow
        body = r.text[:1200]
        rec["body_head"] = body
        # Try to keep structured bodies structured; they tell us the schema.
        if "json" in rec["content_type"]:
            try:
                rec["json_keys"] = sorted(list(r.json().keys()))[:40] \
                    if isinstance(r.json(), dict) else f"<list len={len(r.json())}>"
            except Exception:
                pass
    except requests.exceptions.ConnectionError:
        rec["error"] = "connection_refused"
    except requests.exceptions.Timeout:
        rec["error"] = "timeout"
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def interesting(rec: Dict[str, Any]) -> bool:
    """A path is interesting if it exists at all — including 401/403/405,
    which tell us the route is real and only auth or verb is wrong."""
    s = rec.get("status")
    return s is not None and s not in (404, 501)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://the gateway endpoint")
    ap.add_argument("--token", default=None,
                    help="Bearer token, if the gateway needs one")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.token:
        requests.Session().headers.update({"Authorization": f"Bearer {args.token}"})

    report: Dict[str, Any] = {"base": args.base, "capabilities": {}}

    for cap, paths in CANDIDATES.items():
        hits = []
        for p in paths:
            rec = probe(args.base, p, "GET")
            if interesting(rec):
                hits.append(rec)
                continue
            # If GET 404s, try OPTIONS — some gateways only route POST.
            opt = probe(args.base, p, "OPTIONS")
            if interesting(opt):
                hits.append(opt)
                continue
            # Read-only POST probe where we have a safe payload.
            if cap in READ_ONLY_POST_PROBES:
                for key, q in READ_ONLY_POST_PROBES[cap].items():
                    pr = probe(args.base, p, "POST", {key: q})
                    if interesting(pr):
                        pr["probe_payload_key"] = key
                        hits.append(pr)
                        break
        report["capabilities"][cap] = {
            "found": len(hits) > 0,
            "endpoints": hits if args.verbose else [
                {k: v for k, v in h.items() if k != "body_head"} for h in hits
            ],
        }

    # Verdict against the six protocol requirements.
    caps = report["capabilities"]
    report["verdict"] = {
        "1_raw_query_BLOCKING": caps["query_execution"]["found"],
        "2_mcp_endpoint": caps["mcp"]["found"],
        "3_framework_read": caps["framework_read"]["found"],
        "4_snapshot_restore": caps["snapshot"]["found"],
        "5_mutation_BLOCKING_for_E2": caps["mutation"]["found"],
        "6_introspection": caps["introspection"]["found"],
    }
    blocking = [k for k, v in report["verdict"].items()
                if "BLOCKING" in k and not v]
    report["blocking_gaps"] = blocking

    json.dump(report, sys.stdout, indent=2)
    print(file=sys.stderr)
    if blocking:
        print(f"BLOCKING GAPS: {blocking}", file=sys.stderr)
        print("If raw query execution is missing, there is no deterministic "
              "ground truth and the study cannot proceed as designed.",
              file=sys.stderr)
    else:
        print("No blocking gaps detected.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
