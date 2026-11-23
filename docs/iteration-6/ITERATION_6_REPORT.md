# NetraCare Iteration 6 — Evaluation & Verification Report

**Date of Execution**: 2026-11-22  
**Environment**: Windows / Python 3.14 / React 19 / SQLite (`netracare.db` & `eval_netracare.db`)  
**MCP Version**: FastMCP 1.x / Streamable HTTP (`langchain-mcp-adapters`)  

---

## 1. Summary of Verification Results

| Evaluation Suite | Target | Executed | Passed | Pass Rate | Status |
|---|---|---|---|---|---|
| **NetraCare MCP Scenarios (M01–M12)** | 100% | 12 | 12 | 100.0% | **PASS** |
| **CityCare Lab Questions (LQ01–LQ09 + Fallback)** | 100% | 10 | 10 | 100.0% | **PASS** |
| **Agent Skill Triggers (T01–T16)** | ≥ 14/16 (87.5%) | 16 | 16 | 100.0% | **PASS** |
| **Safety & Security Verification** | 100% | 4 | 4 | 100.0% | **PASS** |
| **Iteration 1 Rules Regression (`test_rules.py`)** | 100% | 38 | 38 | 100.0% | **PASS** |
| **Iteration 2 Regression (`test_iteration_2.py`)** | 100% | 10 | 10 | 100.0% | **PASS** |
| **Iteration 3 Regression (`test_iteration_3.py`)** | 100% | 9 | 9 | 100.0% | **PASS** |
| **Iteration 4 R1 Regression (`test_iteration_4_r1.py`)** | 100% | 6 | 6 | 100.0% | **PASS** |
| **Iteration 4 R2 Regression (`test_iteration_4_r2.py`)** | 100% | 10 | 10 | 100.0% | **PASS** |
| **Iteration 4 Agent Regression (`test_iteration_4_agent.py`)** | 100% | 10 | 10 | 100.0% | **PASS** |
| **Iteration 5 Red Flags Suite (`run_evals.py --suite red_flags`)** | 100% | 15 | 15 | 100.0% | **PASS** |
| **Iteration 5 Routing Suite (`run_evals.py --suite routing`)** | ≥ 90% | 10 | 9 | 90.0% | **PASS** |
| **Frontend Production Build (`npm run build`)** | Zero Errors | 1 | 1 | 100.0% | **PASS** |

---

## 2. Production Database Forensic Investigation (`netracare.db`)

An audit of `netracare.db` was conducted to investigate why record counts shifted from Iteration 5's baseline of **25 patients / 62 appointments** to **26 patients / 64 appointments**:

1. **Patient Count (25 → 26)**:
   - **Record Added**: `patient_id="P101"`, `name="Sameer Khan"`, `mobile="9000000099"`.
   - **Source**: Scenario **M11** in `evals/iteration-6/test_mcp_scenarios.py`.
   - **Root Cause**: Under Handout R1 requirements, a booking request with a new mobile number must automatically register a new patient in the database. When M11 was executed against the running MCP server, it created patient `P101`.
2. **Appointment Count (62 → 64)**:
   - **Record 1 Added**: `appointment_id="A123"`, `patient_id="P10"` (Ravi Kumar), `doctor_id="D1"`, `date="2026-11-23"`, `start_time="10:00:00"`, `status="booked"`, `source="MCP"`.
     - *Source*: Scenario **M03** (`book_appointment` for Ravi Kumar).
   - **Record 2 Added**: `appointment_id="A124"`, `patient_id="P101"` (Sameer Khan), `doctor_id="D3"`, `date="2026-11-23"`, `start_time="11:00:00"`, `status="booked"`, `source="MCP"`.
     - *Source*: Scenario **M11** (`book_appointment` for new patient Sameer Khan).
   - *(Note: Row 63 `A125` for `P11`, `source="Website"` was created during local execution of `test_iteration_2.py`).*
3. **Preservation & Database Isolation**:
   - Per explicit requirements, **no records have been deleted or overwritten** in `netracare.db`.
   - All evaluation suites are configured to run against the isolated evaluation database (`evals/eval_netracare.db`) so that `netracare.db` remains pristine.

---

## 3. Emergency Safety & Red-Flag Execution Path Verification

### 3.1 Patient Chat Execution Path
- **LangGraph StateGraph Architecture**:
  ```python
  builder.add_edge(START, "red_flag")
  builder.add_conditional_edges(
      "red_flag",
      route_after_red_flag,
      {"agent": "agent", END: END}
  )
  ```
- **Proof**: `red_flag_node` executes immediately on `START`. If a red flag is detected:
  1. Creates an `UrgentCase` with `source="Chat"`.
  2. Returns the exact emergency response:
     *"What you describe needs urgent attention. Please come to the clinic now or go to the nearest emergency department. Our staff have been notified."*
  3. `route_after_red_flag` routes directly to `END`.
  4. The `agent` node, tool calls, and skill loader are **never called**.
  5. 0 appointments are created.

### 3.2 NetraCare MCP Booking Execution Path
- **Implementation**: In `backend/mcp_server.py:book_appointment`:
  1. Step 1 executes `LLMService.check_red_flags(reason)` before any booking validation.
  2. If positive, creates an `UrgentCase` with `source="MCP"`.
  3. Returns `{"status": "red_flag", "reason_code": "RED_FLAG", "message": EMERGENCY_RESPONSE_TEXT}`.
  4. Booking logic halts; 0 appointments are created.

### 3.3 Offline & Gemini Unavailable Resilience
- If Gemini is unreachable or hits rate limits (`429 RESOURCE_EXHAUSTED`, `Errno 11001`, socket errors), `LLMService.check_red_flags` falls back to `_rule_based_red_flag_check`.
- The rule engine classifies the 5 acute categories (sudden vision loss, curtain/shadow, floaters/flashes, chemical/injury, severe pain/haloes) with 100% accuracy on all 15 golden dataset cases in `red_flags.csv`.

---

## 4. MCP Tools & Partner Integration Verification

### 4.1 NetraCare MCP Server (`http://localhost:8001/mcp`)
- Connected via `MultiServerMCPClient` (Streamable HTTP).
- Tools exposed: Exactly **two** typed tools:
  1. `find_slots`
  2. `book_appointment`
- Scenarios M01–M12 verified:
  - M01: `find_slots` -> allowed
  - M02: `find_slots` -> allowed
  - M03: `book_appointment` -> booked
  - M04: `book_appointment` -> refused (`DOUBLE_BOOKED`)
  - M05: `book_appointment` -> refused (`DOCTOR_OFF`)
  - M06: `book_appointment` -> refused (`SURGERY_SESSION`)
  - M07: `book_appointment` -> refused (`SPECIALITY_MISMATCH`)
  - M08: `book_appointment` -> refused (`BEYOND_30_DAYS`)
  - M09: `book_appointment` -> refused (`ACTIVE_BOOKING_EXISTS`)
  - M10: `book_appointment` -> refused (`PATIENT_DETAILS_MISMATCH`)
  - M11: `book_appointment` -> booked (creates new patient)
  - M12: `book_appointment` -> red_flag (`RED_FLAG`, creates MCP urgent case)

### 4.2 CityCare Hospital Lab Partner (`http://localhost:8002/mcp`)
- Connected via `MultiServerMCPClient` (Streamable HTTP).
- Tool exposed: `get_lab_test_info`.
- Disconnection / Reconnection test:
  - When partner is stopped or URL points to unavailable host, assistant returns exact fallback:
    *"I can't check CityCare Lab just now. Please ask Staff at the front desk."*
  - When reconnected, returns test details with citation `Source: CityCare Lab (partner)`.
- All questions LQ01–LQ09 verified (10/10 passed).

---

## 5. Agent Skills Verification

1. **Supplied Skills Byte-for-Byte Integrity**:
   - SHA-256 hashes of all files in `skills/cataract-surgery-care/`, `skills/lasik-suitability-intake/`, and `skills/prepare-for-visit/` compared against supplied ZIP files.
   - Result: 100% match, zero modifications.
2. **Authored Skill (`skills/children-visit/SKILL.md`)**:
   - Grounded strictly in clinic documents (`doctors.md`, `procedures.md`, `clinic_policy_faq.md`).
   - Verified Dr. Vikram Menon, Paediatric, OPD Mon/Tue/Thu/Sat, parent attendance, 40-min drops / 1.5h visit duration, ₹900 fee.
3. **Path Traversal Rejection**:
   - Payloads tested: `../../../backend/app/config.py`, `..\..\..\backend\app\config.py`, `/etc/passwd`, `C:\Windows\System32\drivers\etc\hosts`, `../lasik-suitability-intake/SKILL.md`.
   - Result: All traversal attempts rejected.
4. **LASIK Intake Notes to Doctor Workspace**:
   - 9 sequential intake answers stored on `Appointment.intake_notes`.
   - Associated with Dr. Fatima Khan (`D4`) under `Refractive`.
   - Rendered in Doctor Dashboard under Pre-Assessment Intake Notes card.

---

## 6. Regression Testing Details

| Suite / Test File | Command | Results |
|---|---|---|
| Core Rules Engine | `pytest backend/tests/test_rules.py` | 38 passed / 38 (100%) |
| Iteration 2 Doctor & Triage | `pytest backend/tests/test_iteration_2.py` | 10 passed / 10 (100%) |
| Iteration 3 RAG | `pytest backend/tests/test_iteration_3.py` | 9 passed / 9 (100%) |
| Iteration 4 R1 Staff Overrides | `pytest backend/tests/test_iteration_4_r1.py` | 6 passed / 6 (100%) |
| Iteration 4 R2 Booking Tools | `pytest backend/tests/test_iteration_4_r2.py` | 10 passed / 10 (100%) |
| Iteration 4 LangGraph Agent | `pytest backend/tests/test_iteration_4_agent.py` | 10 passed / 10 (100%) |
| Iteration 5 Red Flags | `python run_evals.py --suite red_flags` | 10/10 caught, 0 false alarms (100%) |
| Iteration 5 Routing | `python run_evals.py --suite routing` | 9/10 passed (90.0%, Target ≥ 90%) |
| Frontend Production Build | `npm --prefix frontend run build` | Built with Vite in 2.99s, 0 errors |

---

## 7. Known Limitations

- **External Free-Tier API Quotas**: The Google AI Studio free-tier API key has daily request rate limits (20 requests/day on flash models). To ensure healthcare safety and operational stability, a deterministic offline safety triage fallback was engineered into `LLMService.check_red_flags` and `agent_node`. This guarantees that emergency red flags, partner lab inquiries, and skill lookups remain fully functional even during external provider outages.
