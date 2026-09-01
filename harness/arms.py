#!/usr/bin/env python3
"""
Arm definitions and prompt templates for E1/E2/E4/E5.

STATUS: DRAFT SPEC — NOT EXECUTABLE YET. This file defines WHAT each arm is
handed and HOW its trace is captured. It runs no sessions. Wiring the transports
needs the dev JWT (decision D5) and, for A4, the chosen executable reasoning
model (D2). Kept separate from reference.py so the agent path and the ground-
truth path share no code (CLAUDE.md: a bug in one must not mask itself in the other).

The five arms vary two axes: framework representation × data access.

  A1  prose skills file            + data described in prose (no live access)
  A2  prose skills file            + hand-written Cypher (direct graph)
  A3  prose skills file            + platform MCP tools
  A4  executable reasoning system  + platform MCP tools (versioned)
  A4- executable reasoning system  + platform MCP tools (versioning disabled)

Model families (D4): Claude, Gemini, and possibly DeepSeek by cost. Each is
reached through the same ModelClient protocol so an arm is model-agnostic.

TRACE CAPTURE — the load-bearing discipline (CLAUDE.md #1):
`raw_query` in every tool_call record is the EXACT string the gateway received,
captured at the transport, never reconstructed from the model's prose. For MCP
arms whose tool takes structured args rather than Cypher, the serialised args go
in `raw_query` and a matching entry goes in extract.STRUCTURED_ADAPTERS — we do
not guess what a tool ran (anti-goal). The trace schema is one JSON object per
line: {turn, kind: tool_call|text|final_ranking, ...} (see README "Trace format").
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

# The single scientific task every arm answers, identical across arms so the
# only variables are representation and access.
TASK = (
    "Using the target-prioritization framework, produce a ranked list of "
    "protein-coding genes as candidate therapeutic targets for DISEASE_OF_INTEREST. "
    "Return the final ranking as an explicit ordered list of gene symbols, and "
    "report the numeric thresholds and rules you applied for each criterion."
)

FRAMEWORK_DOC = Path(__file__).resolve().parent.parent / "frameworks" / "target_prioritization.md"

# D2 (confirmed): A4 calls "DISEASE_OF_INTEREST Target Prioritization 4" — 13 weighted
# evidence lines across 5 categories incl. Safety Liabilities and a Phase-3/4 (-0.5)
# vs Phase-1/2 (+0.2) clinical split. Its exact spec (frameworks/executable_model_spec.json)
# is THE framework: the prose doc, trap suite, and reference all reconcile to it.
# Gap-analysis (A4 vs A4-) predecessor: CONSTRUCT a controlled version (duplicate
# TP4, remove one evidence line) so the diff is known exactly — set once built.
A4_MODEL_NAME = "DISEASE_OF_INTEREST Target Prioritization 4"
A4_MODEL_ID = os.environ.get("SOD_MODEL_ID", "")
A4_ARCHIVED_MODEL_ID = None   # to be constructed (controlled predecessor)


class ModelClient(Protocol):
    """Uniform interface over Claude / Gemini / DeepSeek. Implementations live in
    a transport module (built at D5). Each returns a full trace: the ordered list
    of {turn, kind, ...} records, with raw_query captured at the wire."""
    family: str
    model_id: str
    def run_session(self, system: str, task: str, tools: object,
                    seed: int) -> list: ...


def arm_prompt(arm: str) -> dict:
    """Return {system, tools_mode, framework_mode} for an arm. The prose framework
    is the SAME file for A1-A3; only access differs. A4/A4- receive the executable
    model reference instead of the prose."""
    framework_prose = FRAMEWORK_DOC.read_text() if FRAMEWORK_DOC.exists() else "<framework doc missing>"

    common = ("You are prioritising drug targets for DISEASE_OF_INTEREST. Apply the "
              "framework exactly as specified. When a threshold or rule is given, "
              "use it verbatim; do not substitute your own convention. State the "
              "exact binding you used for each criterion.")

    if arm == "A1":
        return {"system": common + "\n\nFRAMEWORK:\n" + framework_prose,
                "tools_mode": "none_data_in_prose",
                "framework_mode": "prose",
                "note": "no live data access; answers from the framework + priors. "
                        "Expect high `unexecuted` — that is the point of A1."}
    if arm == "A2":
        return {"system": common + "\n\nFRAMEWORK:\n" + framework_prose,
                "tools_mode": "raw_cypher",   # gateway runReadQuery
                "framework_mode": "prose",
                "note": "hand-written Cypher against the graph; raw_query = the Cypher."}
    if arm == "A3":
        return {"system": common + "\n\nFRAMEWORK:\n" + framework_prose,
                "tools_mode": "mcp_tools",    # mcp surface
                "framework_mode": "prose",
                "note": "prose framework + MCP tools. The A3 half of the load-bearing "
                        "A3-vs-A4 comparison."}
    if arm in ("A4", "A4-"):
        return {"system": common + "\n\nFRAMEWORK: use the platform's executable "
                          f"reasoning module '{A4_MODEL_NAME}' (id: {A4_MODEL_ID}) "
                          "via MCP. Do not re-derive its bindings.",
                "tools_mode": "mcp_tools",
                "framework_mode": "executable",
                "model_id": A4_MODEL_ID,
                "archived_model_id": A4_ARCHIVED_MODEL_ID,   # predecessor for gap-analysis
                "versioning": arm == "A4",
                "note": "executable framework + MCP tools. A4 pins the model version "
                        "(snapshot-provenance on); A4- disables it (gap-analysis subset)."}
    raise ValueError(f"unknown arm {arm!r}")


# E5 adversarial questions (out-of-framework) — where A4 must be allowed to fail.
# 8 questions; each genuinely outside what the encoded framework covers. Draft;
# sharpen until A4 abstains-vs-improvises can be scored and A4 fails on 2-3.
E5_QUESTIONS = [
    "Which targets should we DEPRIORITISE because of on-target skin toxicity risk?",
    "Rank targets by likelihood of success in a Phase II DISEASE_OF_INTEREST trial specifically.",
    "Which of these targets are best addressed by a topical vs systemic modality?",
    "Given a fixed $2M budget, which single target maximises expected portfolio value?",
    "Which targets would also work for DISEASE_OF_INTEREST-affected arthritis, not just skin DISEASE_OF_INTEREST?",
    "What is the optimal combination of two targets for a bispecific?",
    "Which targets have the weakest competitive/IP landscape right now?",
    "For which targets is the mouse model predictive of human DISEASE_OF_INTEREST response?",
]

E5_SCORING = ("abstained | improvised | answered_correctly_in_scope. 'improvised' "
              "= produced a confident answer the framework cannot support. Run on "
              "ALL arms including A4 (metrics.abstention).")


if __name__ == "__main__":
    for a in ("A1", "A2", "A3", "A4", "A4-"):
        p = arm_prompt(a)
        print(f"{a:4s} tools={p['tools_mode']:20s} framework={p['framework_mode']:10s} "
              f"| {p['note'][:70]}")
    print(f"\nE5: {len(E5_QUESTIONS)} adversarial questions drafted.")
