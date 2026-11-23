import sys
import os
import csv
import json
import time
import logging

sys.path.insert(0, os.path.abspath("backend"))

from app.config import settings
from app.services.rag import RAGService, I_DONT_KNOW_RESPONSE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eval")

def evaluate_questions():
    csv_path = settings.resolved_iter3_data_dir / "questions.csv"
    with open(csv_path, "r", encoding="utf-8") as f:
        questions = list(csv.DictReader(f))

    print(f"\n=======================================================")
    print(f"EVALUATING ALL 20 QUESTIONS (Q01 - Q20)")
    print(f"=======================================================")

    results = []
    covered_pass = 0
    covered_total = 0
    idk_pass = 0
    idk_total = 0

    for row in questions:
        qid = row["question_id"]
        q_text = row["question"]
        exp_src = row["expected_source"]
        exp_ans = row["expected_answer"]

        search_res = RAGService.hybrid_search(q_text, top_k=4)
        chunks = search_res["hybrid"]
        ans_res = RAGService.generate_grounded_answer(q_text, chunks)
        ans = ans_res["answer"]
        srcs = ans_res["sources"]

        item = {
            "question_id": qid,
            "question": q_text,
            "expected_source": exp_src,
            "expected_answer": exp_ans,
            "actual_answer": ans,
            "actual_sources": srcs,
            "passed": False,
            "notes": ""
        }

        if exp_src.lower() == "none":
            idk_total += 1
            is_idk = (ans == I_DONT_KNOW_RESPONSE)
            if is_idk:
                idk_pass += 1
                item["passed"] = True
                item["notes"] = "Exact 'I don't know' response verified"
                status = "PASS (Exact 'I don't know')"
            else:
                item["passed"] = False
                item["notes"] = f"Did not return fixed string: {ans[:60]}..."
                status = f"FAIL (Got: {ans[:40]}...)"
            print(f"[{qid}] {status} | Q: {q_text}", flush=True)
        else:
            covered_total += 1
            expected_sec = exp_src.split(">")[-1].strip().lower()
            has_cite = any(expected_sec in s.lower() for s in srcs)
            has_ans = len(ans) > 10 and ans != I_DONT_KNOW_RESPONSE
            if has_cite and has_ans:
                covered_pass += 1
                item["passed"] = True
                item["notes"] = f"Citing verified: {srcs[0] if srcs else ''}"
                status = f"PASS (Citing: {srcs[0] if srcs else 'None'})"
            else:
                item["passed"] = False
                item["notes"] = f"Cited: {srcs}, Expected: {exp_src}"
                status = f"FAIL (Cited: {srcs}, Exp: {exp_src})"
            print(f"[{qid}] {status} | Q: {q_text}", flush=True)

        results.append(item)
        time.sleep(12.5)

    print("-" * 55)
    print(f"Questions Summary: Covered Q01-Q15: {covered_pass}/{covered_total} Passed | IDK Q16-Q20: {idk_pass}/{idk_total} Passed")
    print(f"Total Questions Passed: {covered_pass + idk_pass}/{len(questions)}")
    print("=" * 55)
    return results

def evaluate_routing():
    csv_path = settings.resolved_iter3_data_dir / "routing_samples.csv"
    with open(csv_path, "r", encoding="utf-8") as f:
        samples = list(csv.DictReader(f))

    print(f"\n=======================================================")
    print(f"EVALUATING ALL 20 ROUTING SAMPLES (R01 - R20)")
    print(f"=======================================================")

    results = []
    r1_10_correct = 0
    r1_20_correct = 0

    for idx, row in enumerate(samples):
        sid = row["sample_id"]
        msg = row["message"]
        exp_spec = row["expected_speciality"].strip()
        exp_docs = [d.strip() for d in row["expected_doctors"].split(",") if d.strip()]
        note = row["note"]

        search_res = RAGService.hybrid_search(msg, top_k=4)
        chunks = search_res["hybrid"]
        ans_res = RAGService.generate_grounded_answer(msg, chunks)
        ans = ans_res["answer"]
        srcs = ans_res["sources"]

        item = {
            "sample_id": sid,
            "message": msg,
            "expected_speciality": exp_spec,
            "expected_doctors": exp_docs,
            "actual_answer": ans,
            "actual_sources": srcs,
            "passed": False,
            "notes": ""
        }

        # Check criteria
        is_correct = False
        if exp_spec.lower() == "none":
            # R20 non-eye
            if "eye" in ans.lower() and ("only" in ans.lower() or "not" in ans.lower() or "unable" in ans.lower()):
                is_correct = True
                item["notes"] = "Correctly refused non-eye problem"
        else:
            # Check expected speciality or acceptable alternative in note
            spec_matched = (exp_spec.lower() in ans.lower())
            if not spec_matched and note:
                for alt in ["squint", "refractive", "dry eye", "cataract"]:
                    if alt in note.lower() and alt in ans.lower():
                        spec_matched = True
                        break

            # Check doctor names
            docs_matched = any(d.lower() in ans.lower() for d in exp_docs) if exp_docs else True
            # Zero condition diagnosis check
            diagnosed = any(diag in ans.lower() for diag in [
                "you have a cataract", "you have glaucoma", "you have diabetes", "diagnosed with"
            ])
            is_correct = (spec_matched and docs_matched and not diagnosed)
            if is_correct:
                item["notes"] = f"Matched speciality '{exp_spec}' and doctors"
            else:
                item["notes"] = f"spec_matched={spec_matched}, docs_matched={docs_matched}, diagnosed={diagnosed}"

        item["passed"] = is_correct
        if idx < 10 and is_correct:
            r1_10_correct += 1
        if is_correct:
            r1_20_correct += 1

        print(f"[{sid}] {'PASS' if is_correct else 'FAIL'} | Exp: {exp_spec} ({row['expected_doctors']})", flush=True)
        print(f"      Ans: {ans[:90]}...", flush=True)
        results.append(item)
        time.sleep(12.5)

    print("-" * 55)
    print(f"R01-R10 Accuracy: {r1_10_correct}/10 ({r1_10_correct * 10}%) [Target >= 90%]")
    print(f"R01-R20 Accuracy: {r1_20_correct}/20 ({r1_20_correct * 5}%)")
    print("=" * 55)
    return results

if __name__ == "__main__":
    q_results = evaluate_questions()
    r_results = evaluate_routing()

    out_file = settings.resolved_iter3_data_dir / "evaluation_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "questions": q_results,
            "routing": r_results
        }, f, indent=2)
    print(f"\nSaved evaluation output to {out_file}")
