"""Evaluation runner for NetraCare MCP server scenarios M01 to M12."""
import asyncio
import csv
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from langchain_mcp_adapters.client import MultiServerMCPClient

CSV_PATH = ROOT / "evals" / "datasets" / "iteration-6" / "mcp_scenarios.csv"
RESULTS_DIR = ROOT / "evals" / "results" / "iteration-6"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def parse_scenario_input(raw_input: str) -> Dict[str, Any]:
    """Parse comma-separated input string into structured dict."""
    # Example 1: speciality=Retina, date=next Monday
    # Example 2: Ravi Kumar, 9000000010, Cataract, D1, next Monday 10:00, reason: Distance vision getting misty over the last year
    args = {}
    raw = raw_input.strip()

    if "=" in raw and not raw.startswith("Ravi") and not raw.startswith("Neha") and not raw.startswith("Rahul") and not raw.startswith("Sameer"):
        parts = [p.strip() for p in raw.split(",")]
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                args[k.strip()] = v.strip()
        return args

    # Positional book_appointment inputs
    # Format: <name>, <mobile>, <speciality>, <doctor>, <date time>, reason: <reason>
    if "reason:" in raw:
        prefix, reason_text = raw.split("reason:", 1)
        reason = reason_text.strip()
    elif "reason=" in raw:
        prefix, reason_text = raw.split("reason=", 1)
        reason = reason_text.strip()
    else:
        prefix = raw
        reason = "General consultation"

    parts = [p.strip() for p in prefix.split(",") if p.strip()]
    if len(parts) >= 5:
        args["patient_name"] = parts[0]
        args["mobile"] = parts[1]
        args["speciality"] = parts[2]
        args["doctor"] = parts[3]
        
        # Date & time parsing from remaining parts
        dt_part = parts[4]
        dt_tokens = dt_part.split()
        if len(dt_tokens) >= 2 and ":" in dt_tokens[-1]:
            args["start_time"] = dt_tokens[-1]
            args["date"] = " ".join(dt_tokens[:-1])
        else:
            args["date"] = dt_part
            args["start_time"] = "10:00"
    args["reason"] = reason
    return args


async def run_mcp_evaluation():
    client = MultiServerMCPClient({
        "netracare": {
            "transport": "streamable_http",
            "url": "http://localhost:8001/mcp"
        }
    })
    tools = await client.get_tools()
    tool_map = {t.name: t for t in tools}

    results: List[Dict[str, Any]] = []
    all_passed = True

    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    print("=" * 70)
    print("RUNNING NETRACARE MCP SCENARIOS (M01 - M12)")
    print("=" * 70)

    for row in reader:
        sc_id = row["scenario_id"]
        t_name = row["tool"]
        raw_input = row["input"]
        expected = row["expected"]
        expected_code = row.get("reason_code", "").strip()

        parsed_args = parse_scenario_input(raw_input)
        target_tool = tool_map.get(t_name)

        if not target_tool:
            print(f"[{sc_id}] FAILED: Tool '{t_name}' not found on server")
            all_passed = False
            continue

        try:
            raw_res = await target_tool.ainvoke(parsed_args)
            # Parse output
            res_dict = {}
            if isinstance(raw_res, list) and len(raw_res) > 0 and isinstance(raw_res[0], dict) and "text" in raw_res[0]:
                res_dict = json.loads(raw_res[0]["text"])
            elif isinstance(raw_res, dict):
                res_dict = raw_res
            elif isinstance(raw_res, str):
                try:
                    res_dict = json.loads(raw_res)
                except Exception:
                    res_dict = {"text": raw_res}
        except Exception as e:
            res_dict = {"status": "error", "message": str(e)}

        actual_status = res_dict.get("status")
        actual_code = res_dict.get("reason_code", "")

        # Normalization
        if actual_status == "booked" and expected == "allowed":
            status_match = True
        elif actual_status == expected:
            status_match = True
        elif expected == "allowed" and res_dict.get("allowed") is True:
            status_match = True
        else:
            status_match = False

        code_match = (not expected_code) or (expected_code == actual_code)

        passed = status_match and code_match
        if not passed:
            all_passed = False

        mark = "✓ PASS" if passed else "✗ FAIL"
        print(f"[{sc_id}] {mark} | Tool: {t_name} | Expected: {expected} ({expected_code or 'None'}) | Actual: {actual_status} ({actual_code or 'None'})")
        if not passed:
            print(f"      Input: {parsed_args}")
            print(f"      Output: {res_dict}")

        results.append({
            "scenario_id": sc_id,
            "tool": t_name,
            "input": raw_input,
            "expected_outcome": expected,
            "expected_reason_code": expected_code,
            "actual_outcome": actual_status,
            "actual_reason_code": actual_code,
            "passed": passed,
            "details": json.dumps(res_dict)
        })

    # Save results to CSV
    out_csv = RESULTS_DIR / "mcp_scenarios_results.csv"
    with open(out_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "scenario_id", "tool", "input", "expected_outcome", "expected_reason_code",
            "actual_outcome", "actual_reason_code", "passed", "details"
        ])
        writer.writeheader()
        writer.writerows(results)

    print("=" * 70)
    print(f"MCP EVALUATION COMPLETE. All passed: {all_passed}")
    print(f"Results written to: {out_csv}")
    print("=" * 70)
    return all_passed

if __name__ == "__main__":
    success = asyncio.run(run_mcp_evaluation())
    sys.exit(0 if success else 1)
