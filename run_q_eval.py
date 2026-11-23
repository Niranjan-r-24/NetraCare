import sys
import os
import csv
import time
import logging

sys.path.insert(0, os.path.abspath("backend"))

from app.config import settings
from app.services.rag import RAGService, I_DONT_KNOW_RESPONSE

logging.basicConfig(level=logging.INFO)

csv_path = settings.resolved_iter3_data_dir / "questions.csv"
with open(csv_path, "r", encoding="utf-8") as f:
    questions = list(csv.DictReader(f))

print(f"Total questions to evaluate: {len(questions)}")
covered_pass = 0
covered_total = 0
idk_pass = 0
idk_total = 0

for row in questions:
    qid = row["question_id"]
    q_text = row["question"]
    exp_src = row["expected_source"]
    exp_ans = row["expected_answer"]

    # Hybrid retrieval
    search_res = RAGService.hybrid_search(q_text, top_k=4)
    chunks = search_res["hybrid"]
    ans_res = RAGService.generate_grounded_answer(q_text, chunks)
    ans = ans_res["answer"]
    srcs = ans_res["sources"]

    if exp_src.lower() == "none":
        idk_total += 1
        is_idk = (ans == I_DONT_KNOW_RESPONSE)
        if is_idk:
            idk_pass += 1
            status = "PASS (Exact 'I don't know')"
        else:
            status = f"FAIL (Answer: {ans[:40]}...)"
        print(f"[{qid}] {status} | Q: {q_text}", flush=True)
    else:
        covered_total += 1
        expected_sec = exp_src.split(">")[-1].strip().lower()
        has_cite = any(expected_sec in s.lower() for s in srcs)
        has_ans = len(ans) > 10 and ans != I_DONT_KNOW_RESPONSE
        if has_cite and has_ans:
            covered_pass += 1
            status = f"PASS (Citing: {srcs[0] if srcs else 'None'})"
        else:
            status = f"FAIL (Cited: {srcs}, Exp: {exp_src})"
        print(f"[{qid}] {status} | Q: {q_text}", flush=True)
    
    # Delay to respect 5 RPM limit
    time.sleep(12.5)

print("=" * 60)
print(f"SUMMARY QUESTIONS:")
print(f"Covered Questions (Q01-Q15): {covered_pass}/{covered_total} Passed")
print(f"Fixed 'I don't know' (Q16-Q20): {idk_pass}/{idk_total} Passed")
print("=" * 60)
