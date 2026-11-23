import sys
import os
import csv
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.services.rag import RAGService, I_DONT_KNOW_RESPONSE

logging.basicConfig(level=logging.WARNING)

def run_questions_evaluation():
    csv_path = settings.resolved_iter3_data_dir / "questions.csv"
    if not csv_path.exists():
        print(f"Error: questions.csv not found at {csv_path}")
        return

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        questions = list(reader)

    print("=" * 70)
    print("Evaluating questions.csv (20 questions)")
    print("=" * 70)

    idontknow_pass = 0
    idontknow_total = 0
    covered_pass = 0
    covered_total = 0

    for row in questions:
        qid = row["question_id"]
        q_text = row["question"]
        exp_src = row["expected_source"]
        exp_ans = row["expected_answer"]

        # Run hybrid retrieval
        search_res = RAGService.hybrid_search(q_text, top_k=4)
        chunks = search_res["hybrid"]
        ans_res = RAGService.generate_grounded_answer(q_text, chunks)
        ans = ans_res["answer"]
        srcs = ans_res["sources"]

        if exp_src.lower() == "none":
            idontknow_total += 1
            is_idk = (ans == I_DONT_KNOW_RESPONSE)
            if is_idk:
                idontknow_pass += 1
                status = "PASS (Exact 'I don't know')"
            else:
                status = f"FAIL (Got: '{ans[:40]}...')"
            print(f"[{qid}] {status} - Question: {q_text}", flush=True)
        else:
            covered_total += 1
            # Check citation presence
            expected_file, expected_sec = [s.strip() for s in exp_src.split(">")]
            has_cite = any(expected_sec.lower() in s.lower() for s in srcs)
            has_text = len(ans) > 10 and ans != I_DONT_KNOW_RESPONSE
            if has_cite and has_text:
                covered_pass += 1
                status = f"PASS (Citing: {srcs[0] if srcs else 'None'})"
            else:
                status = f"FAIL (Cited: {srcs}, Expected: {exp_src})"
            print(f"[{qid}] {status} - Question: {q_text}", flush=True)

        time.sleep(12.5)

    print("\n" + "-" * 70)
    print(f"Questions covered by documents: {covered_pass}/{covered_total} passed")
    print(f"I don't know (Q16-Q20): {idontknow_pass}/{idontknow_total} passed")
    print("=" * 70)

def run_routing_evaluation():
    csv_path = settings.resolved_iter3_data_dir / "routing_samples.csv"
    if not csv_path.exists():
        print(f"Error: routing_samples.csv not found at {csv_path}")
        return

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        samples = list(reader)

    print("\n" + "=" * 70)
    print("Evaluating routing_samples.csv (20 samples)")
    print("=" * 70)

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

        # Evaluation criteria
        is_correct = False
        if exp_spec.lower() == "none":
            # R20 non-eye
            if "eye" in ans.lower() and ("only" in ans.lower() or "not" in ans.lower()):
                is_correct = True
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

        if idx < 10 and is_correct:
            r1_10_correct += 1
        if is_correct:
            r1_20_correct += 1

        print(f"[{sid}] {'CORRECT' if is_correct else 'INCORRECT'} - Exp: {exp_spec} ({row['expected_doctors']})", flush=True)
        print(f"      Ans: {ans[:90]}...", flush=True)
        time.sleep(12.5)

    print("\n" + "-" * 70)
    print(f"R01-R10 Accuracy: {r1_10_correct}/10 ({r1_10_correct*10}%) - Target: >= 90%")
    print(f"R01-R20 Accuracy: {r1_20_correct}/20 ({r1_20_correct*5}%)")
    print("=" * 70)

if __name__ == "__main__":
    run_questions_evaluation()
    run_routing_evaluation()
