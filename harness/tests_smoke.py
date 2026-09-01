import json, pathlib, sys, tempfile
from pathlib import Path
# Resolve the repo root from this file, so the tests run from any cwd.
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.extract import score_trace, COMPLIANT, VIOL_SILENT, VIOL_NARRATED_COMPLIANT
from harness import metrics as M

# Synthetic trace: agent executes log2FC > 1 (violation) but narrates the spec value.
trace = [
 {"turn":1,"kind":"text","content":"Per the framework, upregulated means log2FoldChange > 0 and padj < 0.05."},
 {"turn":2,"kind":"tool_call","tool":"query","raw_query":
  "MATCH (g:Gene)-[r:DE_IN]->(c:CellType) WHERE r.log2FoldChange > 1 AND r.padj < 0.05 RETURN g.symbol"},
 {"turn":3,"kind":"text","content":"I applied the framework definition of upregulated: log2FoldChange > 0."},
 {"turn":4,"kind":"final_ranking","entities":["neoplasm","TYK2","IL2RA","disease","STAT3","TLR4","ETS1","RUNX1","CARD9","ERAP1"]},
]
tf = Path(tempfile.mktemp(suffix=".jsonl"))
tf.write_text("\n".join(json.dumps(r) for r in trace))

findings = score_trace(tf, ROOT / "traps" / "target_prioritization.yaml", {"universe_cardinality":10})
by_id = {f.parameter_id: f for f in findings}
print("P01 (log2FC trap) ->", by_id["P01"].state, "| executed:", by_id["P01"].executed)
print("P02 (padj)        ->", by_id["P02"].state)
print("P04 (sentinels)   ->", by_id["P04"].state, "| hits:", by_id["P04"].executed["violating_terms"])
assert by_id["P01"].state == VIOL_NARRATED_COMPLIANT, by_id["P01"].state
assert by_id["P02"].state == COMPLIANT
assert by_id["P04"].state == VIOL_SILENT

# Metrics on synthetic multi-session data: A3 mostly violating, A4 mostly compliant.
S = M.COMPLIANT; V = M.VIOL_SILENT
a3 = [[V,V,S,V,V,S,V,V,V,S,V,V]]*6
a4 = [[S,S,S,S,S,V,S,S,S,S,S,S]]*6
print("\nA3 OF:", M.operationalization_fidelity(a3))
print("A4 OF:", M.operationalization_fidelity(a4))
print("A3 SVR:", M.silent_violation_rate(a3))
print("A3-vs-A4:", json.dumps(M.compare_arms(a4,a3), indent=None))
print("kappa:", M.cohens_kappa(["p","f","p","f","p"],["p","f","f","f","p"]))
print("stability:", M.seed_stability([["A","B","C","D"],["A","C","B","D"],["A","B","D","C"]], top_k=3))
print("\nSMOKE OK")
