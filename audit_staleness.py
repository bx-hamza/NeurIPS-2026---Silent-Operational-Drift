#!/usr/bin/env python3
"""Audit the committed analysis files for staleness.

Three specific failures happened during this study and were caught by hand.
Each produced a file that looked plausible and disagreed with the frozen
results, so each is now checked mechanically:

1. **Scored against the contaminated judge.** The first judge run from the
   first vendor was accidentally shown the gold, making it agree with the gold
   almost perfectly. Any analysis whose `vs_claude` block matches its
   `vs_gold` block was computed against that run rather than the blind re-run.

2. **Missing a judge.** A third vendor was added partway through
   (deviation 12). Scripts written before that emit two judge blocks instead
   of three, so a whole vendor silently disappears from the comparison.

3. **Drifting from HANDOFF.** An analysis file can be regenerated with a
   different rater subset or a stale input and no longer match the frozen
   numbers the paper reports.

Run this whenever an analysis file is regenerated:

    python audit_staleness.py

Exit code 0 if everything is current, 1 otherwise.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
ANALYSIS = ROOT / "analysis"
EXPECTED_JUDGES = {"claude", "gemini", "deepseek"}


class Audit:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []

    def ok(self, msg: str) -> None:
        self.passed += 1

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def check(self, cond: bool, msg: str) -> None:
        self.ok(msg) if cond else self.fail(msg)


def judge_blocks(obj: dict) -> dict:
    """Return the vs_<judge> blocks, whether nested under consensus or flat."""
    scope = obj.get("consensus") if isinstance(obj.get("consensus"), dict) else obj
    return {k[3:]: v for k, v in scope.items()
            if k.startswith("vs_") and k != "vs_gold" and isinstance(v, dict)}


def gold_block(obj: dict) -> dict | None:
    scope = obj.get("consensus") if isinstance(obj.get("consensus"), dict) else obj
    g = scope.get("vs_gold")
    return g if isinstance(g, dict) else None


def main() -> int:
    a = Audit()
    handoff = json.load(open(ROOT / "data" / "HANDOFF.json"))
    hs = handoff["adjudication"]["human_subsample"]
    three = handoff["adjudication"]["three_judge"]

    files = sorted(ANALYSIS.glob("*.json"))
    if not files:
        print("no analysis files found")
        return 1

    for path in files:
        obj = json.load(open(path))
        judges = judge_blocks(obj)
        if not judges:
            continue  # not an adjudication file
        name = path.name

        # 1. all three vendors present
        a.check(set(judges) == EXPECTED_JUDGES,
                f"{name}: judge coverage is {sorted(judges)}, expected "
                f"{sorted(EXPECTED_JUDGES)}")

        # 2. not scored against the contaminated run
        gold = gold_block(obj)
        if gold is not None and "claude" in judges:
            same = (judges["claude"].get("kappa") == gold.get("kappa")
                    and judges["claude"].get("agreement") == gold.get("agreement"))
            a.check(not same,
                    f"{name}: vs_claude is identical to vs_gold "
                    f"(kappa={gold.get('kappa')}), which is the signature of "
                    "scoring against judge_claude_LEAKED.json. Re-run against "
                    "the blind re-run judge_claude.json.")

    # 3. the two panel files must match the frozen numbers
    panel_path = ANALYSIS / "human_adjudication_panel.json"
    if panel_path.exists():
        panel = json.load(open(panel_path))
        g = gold_block(panel) or {}
        a.check(g.get("kappa") == hs["consensus_vs_gold"]["kappa"],
                f"full panel consensus-vs-gold kappa {g.get('kappa')} != "
                f"HANDOFF {hs['consensus_vs_gold']['kappa']}")
        a.check(g.get("agreement") == hs["consensus_vs_gold"]["agreement"],
                f"full panel consensus-vs-gold agreement {g.get('agreement')} != "
                f"HANDOFF {hs['consensus_vs_gold']['agreement']}")
        a.check(panel.get("inter_rater", {}).get("fleiss_kappa")
                == hs["inter_rater"]["fleiss_kappa"],
                "full panel Fleiss kappa != HANDOFF")
        a.check(panel.get("n_raters") == hs["n_raters"],
                f"full panel n_raters {panel.get('n_raters')} != HANDOFF "
                f"{hs['n_raters']}")
        got = sorted(round(v["kappa_vs_gold"], 3)
                     for v in panel.get("per_rater", {}).values())
        a.check(got == sorted(hs["per_rater_kappa_vs_gold"]),
                f"full panel per-rater kappas {got} != HANDOFF "
                f"{sorted(hs['per_rater_kappa_vs_gold'])}")
        for vendor, block in judge_blocks(panel).items():
            expected = three["vs_human_consensus_kappa"].get(vendor)
            a.check(block.get("kappa") == expected,
                    f"full panel vs_{vendor} kappa {block.get('kappa')} != "
                    f"HANDOFF {expected}")

    spec_path = ANALYSIS / "human_adjudication_panel_specialists.json"
    if spec_path.exists():
        spec = json.load(open(spec_path))
        sens = hs["specialists_only_sensitivity"]
        a.check(spec.get("n_raters") == sens["n_raters"],
                f"specialists n_raters {spec.get('n_raters')} != HANDOFF "
                f"{sens['n_raters']}")
        a.check(spec.get("inter_rater", {}).get("fleiss_kappa")
                == sens["fleiss_kappa"],
                "specialists Fleiss kappa != HANDOFF")
        g = gold_block(spec) or {}
        a.check(g.get("kappa") == sens["consensus_vs_gold_kappa"],
                f"specialists consensus-vs-gold kappa {g.get('kappa')} != "
                f"HANDOFF {sens['consensus_vs_gold_kappa']}")

    # 4. the judge label files themselves
    adj = ROOT / "adjudication"
    labels = {}
    for vendor in sorted(EXPECTED_JUDGES):
        p = adj / f"judge_{vendor}.json"
        a.check(p.exists(), f"missing judge label file {p.name}")
        if p.exists():
            labels[vendor] = json.load(open(p))
    a.check((adj / "judge_claude_LEAKED.json").exists(),
            "judge_claude_LEAKED.json is missing; the contaminated run ships "
            "deliberately so the remediation can be audited")
    if len(labels) == 3:
        n = {len(v) for v in labels.values()}
        a.check(len(n) == 1 and n.pop() == handoff["adjudication"]["judged_items"],
                "judge label files disagree on item count, or disagree with "
                "HANDOFF.adjudication.judged_items")
        leaked = json.load(open(adj / "judge_claude_LEAKED.json"))
        a.check(labels["claude"] != leaked,
                "judge_claude.json is byte-identical to the leaked run; the "
                "blind re-run has not replaced it")

    total = a.passed + len(a.failures)
    if a.failures:
        print(f"STALE  {a.passed}/{total} checks passed\n")
        for f in a.failures:
            print(f"  - {f}")
        return 1
    print(f"OK     {a.passed}/{total} staleness checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
