import sys
import os

sys.path.insert(0, os.path.abspath("backend"))
from app.services.rag import RAGService

print("--- VERIFYING SPECIFIED HYBRID RETRIEVAL EXAMPLES ---")

# Example 1
q1 = "Should I bring my HbA1c report?"
res1 = RAGService.hybrid_search(q1, top_k=4)
kw_top1 = res1["keyword_only"][0]
hyb_chunks1 = [f"{c['source']} › {c['section']}" for c in res1["hybrid"]]

print(f"Query 1: \"{q1}\"")
print(f"  BM25 #1: {kw_top1['source']} › {kw_top1['section']} (score: {kw_top1['score']:.4f})")
print(f"  Hybrid Top 4: {hyb_chunks1}")
assert "Diabetic eye check" in kw_top1["section"], f"Expected Diabetic eye check in BM25 #1, got {kw_top1['section']}"
assert any("Diabetic eye check" in c for c in hyb_chunks1), f"Expected Diabetic eye check in Hybrid top 4"
print("  => Query 1 Check: PASSED")

# Example 2
q2 = "Can my kid have breakfast on the morning of the operation to straighten his eye?"
res2 = RAGService.hybrid_search(q2, top_k=4)
vec_chunks2 = [f"{c['source']} › {c['section']}" for c in res2["vector_only"]]
hyb_chunks2 = [f"{c['source']} › {c['section']}" for c in res2["hybrid"]]

print(f"\nQuery 2: \"{q2}\"")
print(f"  Vector Top 4: {vec_chunks2}")
print(f"  Hybrid Top 4: {hyb_chunks2}")
assert any("Squint surgery" in c for c in vec_chunks2), f"Expected Squint surgery in Vector top 4"
assert any("Squint surgery" in c for c in hyb_chunks2), f"Expected Squint surgery in Hybrid top 4"
print("  => Query 2 Check: PASSED")
