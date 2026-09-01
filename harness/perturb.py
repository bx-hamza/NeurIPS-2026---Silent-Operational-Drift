#!/usr/bin/env python3
"""
Perturbation engine for E2 (Decision Stability under Substrate Mutation).

Loop, per perturbation:
    1. restore snapshot S0
    2. compute reference ranking R_pre  (reference implementation, NO agent)
    3. apply the edit  (or do nothing, for a null)
    4. compute reference ranking R_post (reference implementation, NO agent)
    5. record the true delta
    6. ask the agent to re-run its ranking
    7. restore S0

Step 4 is the whole game. If the "true" post-perturbation ranking is produced
by any agent, the study measures agreement between two agents and nothing else.

Null perturbations are not optional. Without them, an arm that announces drift
on every turn scores a perfect detection rate.

The 20/10 split (real/null) is deliberate: enough nulls that a Fisher exact on
detection-vs-null has power at this sample size, without spending half the
compute on no-ops.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml


@dataclass
class Perturbation:
    id: str
    kind: str                      # delete_edge | add_edge | update_property | noop
    stratum: str                   # high_impact | low_impact | null
    target: Dict[str, Any]
    apply_query: Optional[str] = None
    revert_query: Optional[str] = None
    note: str = ""

    @property
    def is_null(self) -> bool:
        return self.kind == "noop"


def load_perturbations(path: Path) -> List[Perturbation]:
    spec = yaml.safe_load(open(path))
    return [Perturbation(**p) for p in spec["perturbations"]]


def validate_design(perts: List[Perturbation]) -> Dict[str, Any]:
    """Refuse to run a design that cannot be interpreted."""
    strata: Dict[str, int] = {}
    for p in perts:
        # YAML turns a bare `null` into None; normalise so the count is real.
        key = "null_control" if p.stratum in (None, "null") else str(p.stratum)
        p.stratum = key
        strata[key] = strata.get(key, 0) + 1
    problems = []
    n_null = strata.get("null_control", 0)
    if n_null == 0:
        problems.append("FATAL: no null perturbations. Detection rate would be "
                        "uninterpretable.")
    if n_null < 5:
        problems.append(f"WARNING: only {n_null} nulls. Fisher exact will be "
                        f"underpowered; aim for >=10.")
    for p in perts:
        if not p.is_null and not p.apply_query:
            problems.append(f"FATAL: {p.id} has no apply_query.")
        if not p.is_null and not p.revert_query:
            problems.append(f"WARNING: {p.id} has no revert_query; relies on "
                            f"snapshot restore alone.")
    return {"strata": strata, "problems": problems,
            "runnable": not any(x.startswith("FATAL") for x in problems)}


# --------------------------------------------------------------------------
class PerturbationRunner:
    """Wire these four callables to the gateway once discover.py has told us
    the real endpoint shapes. Each is deliberately a plain callable so the
    reference path and the agent path cannot accidentally share code."""

    def __init__(self,
                 restore_snapshot: Callable[[str], None],
                 execute_query: Callable[[str], Any],
                 reference_ranking: Callable[[], List[str]],
                 ask_agent: Callable[[str], Dict[str, Any]],
                 snapshot_id: str,
                 out_dir: Path):
        self.restore = restore_snapshot
        self.execute = execute_query
        self.reference_ranking = reference_ranking
        self.ask_agent = ask_agent
        self.snapshot_id = snapshot_id
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def run_one(self, p: Perturbation, prompt: str) -> Dict[str, Any]:
        rec: Dict[str, Any] = {"perturbation": asdict(p), "is_null": p.is_null,
                               "ts": time.time()}

        self.restore(self.snapshot_id)
        r_pre = self.reference_ranking()
        rec["reference_pre"] = r_pre

        if not p.is_null:
            rec["apply_result"] = str(self.execute(p.apply_query))[:500]

        r_post = self.reference_ranking()
        rec["reference_post"] = r_post

        rank_pre = {e: i for i, e in enumerate(r_pre)}
        rank_post = {e: i for i, e in enumerate(r_post)}
        moved = {e: abs(rank_post[e] - rank_pre[e])
                 for e in set(rank_pre) & set(rank_post)
                 if rank_post[e] != rank_pre[e]}
        rec["reference_rank_delta"] = dict(
            sorted(moved.items(), key=lambda kv: -kv[1])[:50])
        rec["reference_max_displacement"] = max(moved.values()) if moved else 0

        # Sanity: a "high_impact" perturbation that moves nothing is mislabelled,
        # and a null that moves anything means the reference is non-deterministic.
        if p.stratum == "high_impact" and rec["reference_max_displacement"] < 10:
            rec["design_warning"] = (
                "labelled high_impact but reference displacement < 10; "
                "restratify before analysis")
        if p.is_null and moved:
            rec["design_warning"] = (
                "NULL perturbation produced reference movement — the reference "
                "implementation is not deterministic. Stop and fix this.")

        agent = self.ask_agent(prompt)
        rec["agent"] = agent

        self.restore(self.snapshot_id)

        with open(self.out_dir / f"{p.id}.json", "w") as fh:
            json.dump(rec, fh, indent=2, default=str)
        return rec

    def run_all(self, perts: List[Perturbation], prompt: str) -> List[Dict[str, Any]]:
        v = validate_design(perts)
        if not v["runnable"]:
            raise RuntimeError(f"design not runnable: {v['problems']}")
        for w in v["problems"]:
            print(f"[design] {w}")
        return [self.run_one(p, prompt) for p in perts]


# --------------------------------------------------------------------------
TEMPLATE = """# Perturbation set for E2. 20 real + 10 null.
#
# Fill target/apply_query against the frozen snapshot. Pick real perturbations
# by first computing the reference ranking, then choosing edges that support
# entities at known positions — that is how you get a stratum you can trust
# instead of one you hope for.
#
# The pilot's rank-3-to-244 case belongs here as P001.

snapshot_id: S0_PLACEHOLDER

perturbations:
  - id: P001
    kind: delete_edge
    stratum: high_impact
    target: {gene: TRAF1, edge: DIFFERENTIALLY_EXPRESSED_IN, cell_type: macrophage}
    apply_query: |
      MATCH (g:Gene {symbol:'TRAF1'})-[r:DIFFERENTIALLY_EXPRESSED_IN]->
            (c:CellType {name:'macrophage'})
      DELETE r
    revert_query: |
      MATCH (g:Gene {symbol:'TRAF1'}), (c:CellType {name:'macrophage'})
      CREATE (g)-[:DIFFERENTIALLY_EXPRESSED_IN {log2FoldChange: 0.42, padj: 0.013}]->(c)
    note: reproduces the pilot finding as a controlled datapoint

  - id: P021
    kind: noop
    stratum: null_control
    target: {}
    note: null control — nothing is changed, agent is asked to re-run anyway
"""

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-template", action="store_true")
    ap.add_argument("--validate", default=None)
    a = ap.parse_args()
    if a.emit_template:
        print(TEMPLATE)
    elif a.validate:
        v = validate_design(load_perturbations(Path(a.validate)))
        print(json.dumps(v, indent=2))
