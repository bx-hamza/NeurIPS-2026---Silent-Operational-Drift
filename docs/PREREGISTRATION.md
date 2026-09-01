# Pre-registration and freeze provenance

This study was pre-registered by freezing the measurement instrument in version
control before any scored session ran, and recording the freeze as an annotated,
hashed tag. This document states what that freeze was, what it covered, how the
authors can demonstrate it, and — honestly — what a reader of this anonymised
repository can and cannot check without the private history.

Read it alongside `docs/PROTOCOL.md` (the procedure as actually run) and
`docs/DEVIATIONS.md` (every departure from the frozen plan; an empty list would
itself be a positive claim that nothing changed).

## The freeze

| | |
|---|---|
| Mechanism | annotated Git tag `prereg-v1` |
| Pre-registration hash | `94c5a67f3e15dbad0d60257f341c9b272af254bb` — the tag object's SHA-1 |
| Frozen commit | `38aa0751d108afed7cf0f264aa806dddec191de0` |
| Date | 2026-08-17, before the first scored session |
| Scope (tag message) | frozen E1 protocol — trap suite, per-parameter reference implementations, framework, classifier, and metrics — before scored runs |

The hash **is** the pre-registration: a commitment, fixed at a point in time, to
the exact instrument the study would be scored with. The paper cites this value.

## What the freeze covers

The E1 measurement instrument, in the state it was scored in:

- the **trap suite** — `traps/target_prioritization.yaml` (each instrumented
  parameter's specified binding, its pre-registered plausible-wrong
  alternatives, and the `underdetermined` flag);
- the **agent-free reference** — `harness/reference.py` (the hand-written
  per-parameter queries E1 is scored against, computed with no agent in the loop);
- the **framework**, in both representations — the prose
  `frameworks/target_prioritization.md` and the executable
  `frameworks/executable_model_spec.json`;
- the **fidelity classifier** — `harness/extract_tp4.py`;
- the **metric definitions** — `harness/metrics.py`.

After the freeze these are not edited. A necessary change means a new tag, a new
hash, and a line in `docs/DEVIATIONS.md`. The E2 artifacts were frozen
separately, before E2 ran (`docs/DEVIATIONS.md`, item 7).

## What was pre-registered

The frozen plan is recoverable as **`docs/PROTOCOL.md` minus the changes logged
in `docs/DEVIATIONS.md`**: `PROTOCOL.md` describes the procedure as actually run,
and every point where the run departed from the freeze is a numbered line in
`DEVIATIONS.md`. In summary, what was fixed before any result existed:

- **Hypothesis.** A prose framework is an underdetermined specification; an agent
  executing it binds the underdetermined instructions at run time; those bindings
  can each be defensible, openly disclosed, and fully compliant on every checkable
  instruction, and still invert the scientific conclusion. **A3 versus A4** — tool
  access held constant, only the representation varied — is the load-bearing test.
- **Arms.** A1 prose / no data · A2 prose / raw queries · A3 prose / tools ·
  A4 executable model / tools. A3-vs-A4 is primary; A1 and A2 bracket it.
- **Experiments.** E1 fidelity vs. divergence; E2 substrate mutation with
  mandatory null controls; E3 within-arm stability; E4 re-walk reproduction;
  E5 adversarial probing; E7 operational cost.
- **Metrics.** Decision divergence (top-10 Jaccard against A4) is the **primary**
  metric by design; operationalization fidelity is the metric that a practitioner
  reaches for and that cannot see the failure. `unexecuted` is excluded from the
  OF denominator. Intervals are clustered bootstrap over sessions, never over
  parameter observations.
- **Pre-committed reading rules.** A confidence interval spanning zero is a null
  result — with one declared exception: the A3-vs-A4 fidelity difference is
  *expected* to span zero, because the claim is that both arms are compliant and
  compliance is therefore not sufficient; the 0.000 point estimate is never to be
  presented as a positive finding. A null perturbation that moved the reference
  ranking would halt the study. Adjudication requires κ ≥ 0.6.

None of these was changed after the freeze. Where the *execution* later departed —
added model families, the human-panel upgrade, the third judge and the blinded
re-run — each is a numbered line in `docs/DEVIATIONS.md`, not a silent edit.

## Verifying the freeze

**What this anonymised repository lets you check now:**

- The frozen instrument files listed above are all present and internally
  consistent.
- `python verify_numbers.py` re-derives every numeric claim in the paper from
  `data/HANDOFF.json` (`OK 94/94`).
- `python audit_staleness.py` confirms the committed analysis files are current:
  all three judges present, none scored against the contaminated judge run, and
  no drift from the frozen numbers.
- `docs/DEVIATIONS.md` is populated — the freeze is not claimed to have held
  unchanged.

**What requires the authors' private history.** This repository is published under
a fresh, anonymous Git history (see `RELEASE_CHECKLIST.md`), so the tag below does
not resolve here. In the study's own repository the freeze is byte-verifiable, and
the authors can demonstrate it to the program committee or an area chair on
request. There:

```
git rev-parse prereg-v1                                # -> 94c5a67f3e15dbad0d60257f341c9b272af254bb
git cat-file -t prereg-v1                              # -> tag   (annotated)
git show --no-patch --format=%ci prereg-v1^{commit}    # -> 2026-08-17 ..., before any scored run
git show prereg-v1:<frozen-file> | sha256sum           # recover and hash any frozen artifact
```

## Honesty caveats

1. **The published files do not hash to the pre-registration.** This repository is
   anonymised (therapeutic area, platform, and infrastructure identifiers renamed —
   see `docs/HARNESS_MANIFEST.md`) and re-committed under a fresh anonymous history.
   Anonymisation edits bytes, so no released file matches its frozen hash, and
   `94c5a67...` is a commitment against the **private** original. Nothing but
   identifiers was changed — no hypothesis, arm, metric, threshold, weight, binding,
   or decision rule. The anonymised-to-actual mapping is held by the authors and is
   supplied to reviewers or an area chair on request.
2. **Every post-freeze change is logged.** `docs/DEVIATIONS.md` is the honest
   counter-record (thirteen entries, matching the paper's Appendix E). None altered
   a frozen artifact, a measured binding, a threshold, or a weight.
3. **This is a freeze, not an external registry entry.** It proves the instrument
   was fixed before the results existed and is byte-verifiable in the authors'
   history; it was not lodged with an external registry such as OSF or AsPredicted.
