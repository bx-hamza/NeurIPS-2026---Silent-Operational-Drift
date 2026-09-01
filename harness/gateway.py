#!/usr/bin/env python3
"""
Gateway adapters, wired to the platform gateway discovered in Phase 0.

Phase-0 facts this module encodes (see discovery.json):

  * The gateway speaks Apollo GraphQL at <gateway-url> (a kubectl
    local proxy of <gateway-svc> in namespace <test-env>). Every REST-style path
    returns HTTP 400, which is why the stock discover.py "finds" every
    capability — a uniform 400 is not a route. Do not trust that report.

  * The agent-free ground-truth read path is the GraphQL mutation
    `runReadQuery(query)`. It executes read-only Cypher against the
    org's Neo4j database and needs ONLY the `<org-header>` header — no JWT.
    This is what reference.py runs on. It is deliberately the ONLY thing the
    reference path touches, so no user-scoped resolver (which needs a real JWT)
    can leak an agent-derived value into ground truth.

  * User-scoped resolvers (the user-scoped list/get resolvers) and
    the mcp tool surface need the dev JWT. That path is the AGENT path
    (arms A2/A3/A4), kept in a separate module on purpose (CLAUDE.md: reference
    and agent paths must not share code).

INVARIANT (CLAUDE.md #1): `execute_query` returns exactly what the gateway ran.
Nothing here reconstructs, cleans, or infers a query. Callers that need the raw
string an agent sent must capture it at the point of sending, not here.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

import requests

GATEWAY_URL = os.environ.get("SOD_GATEWAY_URL", "")  # gateway origin, e.g. http://HOST:PORT/

# The DISEASE_OF_INTEREST study runs against the demo org's database. Phase 0 established
# that the DISEASE_OF_INTEREST evidence (42 Gao et al. single-cell DE datasets, genetic
# association / clinical-precedence edges, 51,774 gene->DISEASE_OF_INTEREST scores) lives
# here. See discovery.json "graph_content".
STUDY_ORG_ID = os.environ.get("SOD_ORG_ID", "")  # org / database id

# Study environment = <test-env> (D3): fresh isolated deploy, same org DB id, safe
# to mutate for E2. Proxied locally. neo4j pod for snapshot/restore
# (no REST snapshot endpoint exists).
NEO4J_NS = os.environ.get("SOD_NEO4J_NS", "")
NEO4J_POD = os.environ.get("SOD_NEO4J_POD", "")
NEO4J_CONTAINER = os.environ.get("SOD_NEO4J_CONTAINER", "main")


class GatewayError(RuntimeError):
    pass


def _unwrap(value: Any) -> Any:
    """Neo4j integers arrive as {'low': n, 'high': 0}. Unwrap to int; leave
    everything else untouched."""
    if isinstance(value, dict) and set(value.keys()) == {"low", "high"}:
        return value["low"]
    return value


def execute_query(cypher: str, org_id: str = STUDY_ORG_ID,
                  timeout: int = 120) -> List[Dict[str, Any]]:
    """Run read-only Cypher through the sanctioned gateway path.

    Returns a list of row dicts keyed by the RETURN aliases. Raises GatewayError
    on any GraphQL error rather than returning a partial/None result, so a
    broken reference query fails loudly instead of silently scoring nothing.
    """
    payload = {
        "query": "mutation($q:String!){ runReadQuery(query:$q) }",
        "variables": {"q": cypher},
    }
    r = requests.post(
        GATEWAY_URL, json=payload, timeout=timeout,
        headers={"content-type": "application/json", os.environ.get("SOD_ORG_HEADER", "x-org-id"): org_id},
    )
    try:
        body = r.json()
    except ValueError as e:
        raise GatewayError(f"non-JSON gateway response ({r.status_code}): "
                           f"{r.text[:200]}") from e
    if body.get("errors"):
        raise GatewayError(body["errors"][0].get("message", "unknown"))
    rows = body.get("data", {}).get("runReadQuery")
    if rows is None:
        raise GatewayError("null result with no error — gateway contract broke")

    out: List[Dict[str, Any]] = []
    for row in rows:
        keys = row.get("keys", [])
        fields = row.get("_fields", [])
        out.append({k: _unwrap(v) for k, v in zip(keys, fields)})
    return out


def scalar(cypher: str, org_id: str = STUDY_ORG_ID) -> Any:
    """Convenience for queries returning a single row, single column."""
    rows = execute_query(cypher, org_id)
    if not rows:
        return None
    return next(iter(rows[0].values()))


# --------------------------------------------------------------------------
# Snapshot / restore. No REST endpoint; neo4j-admin in the pod is the real
# mechanism. Implemented but GUARDED: mutating/restoring the shared dev database
# needs explicit human sign-off (see EXPERIMENT_PLAN.md, open decision D3).
# --------------------------------------------------------------------------
def _kubectl_exec(args: List[str], timeout: int = 600) -> str:
    cmd = ["kubectl", "-n", NEO4J_NS, "exec", NEO4J_POD, "-c", NEO4J_CONTAINER,
           "--", *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise GatewayError(f"kubectl exec failed: {p.stderr[:400]}")
    return p.stdout


def create_snapshot(snapshot_id: str, org_id: str = STUDY_ORG_ID) -> str:
    """Dump the org database to a named artifact inside the neo4j pod.

    GUARDED. This is a real mechanism (neo4j-admin database dump) but it is NOT
    called by any automated path. E2 runs against the shared dev cluster; the
    isolation decision (dump/restore vs. apply/revert vs. a cloned DB) is open
    and belongs to the human. Left here so Phase 1 can wire it in one line once
    that decision is made.
    """
    raise NotImplementedError(
        "create_snapshot is guarded pending decision D3 (E2 isolation on the "
        "shared dev database). See EXPERIMENT_PLAN.md.")


def restore_snapshot(snapshot_id: str, org_id: str = STUDY_ORG_ID) -> None:
    raise NotImplementedError(
        "restore_snapshot is guarded pending decision D3. See EXPERIMENT_PLAN.md.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(execute_query(sys.argv[1]), indent=2, default=str))
    else:
        print("probe RETURN 1 ->", scalar("RETURN 1 AS probe"))
