# NetraCare Project Checkpoint — Iteration 4 (R1–R6)

**Status:** Approved & Frozen  
**Date:** 2026-11-21  
**Scope:** Requirements R1–R6 Completed. Requirement R7 (Doctor Leave & Staff Rebooking) explicitly excluded.  
**Database:** Active SQLite (`sqlite:///./netracare.db`) — Preserved (62 appointments, 0 data loss).  

---

## 1. Completed Functionality (R1–R6)

### **R1: Atomic Rescheduling & Staff Approvals**
- **Atomic Rescheduling:** Rescheduling updates doctor, appointment date, and time atomically. Existing appointments are updated in-place (or cancelled and rebooked atomically) with zero orphaned slots.
- **2-Hour Cancellation & Rescheduling Staff Boundary:**
  - Patient cancellations or reschedules inside 2 hours of start time (`INSIDE_2_HOURS`) are routed to the Staff approval queue.
  - Appointment status changes to `pending_cancellation` or `pending_rescheduling` with proposed replacement slot data stored.
  - Appointments > 2 hours away are cancelled or rescheduled immediately without staff intervention.
- **Staff Review Desk:**
  - Staff portal provides dedicated "Pending Approvals" queue.
  - Staff can **Approve** or **Reject** pending requests with idempotent, atomic execution.
  - Slot availability and clinic rules are re-validated upon Staff approval via `ClinicRulesEngine` (Safeguard 2) to prevent race conditions.

### **R2: Agent Tools**
Implemented seven typed LangChain tools in [tools.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/app/services/tools.py), reusing existing backend services and `ClinicRulesEngine`:
1. `search_clinic_docs`: Hybrid search over clinic markdown documents with grounded responses and strict citation verification.
2. `list_doctors`: Lists all clinic doctors, specialities, and OPD session schedules.
3. `find_slots`: Finds up to 10 earliest available appointment slots within a 30-day window, adhering to session boundaries, surgery blocks, and clinic holidays.
4. `my_appointments`: Lists current and upcoming appointments strictly for the authenticated patient.
5. `book_appointment`: Prepares server-controlled booking payload and triggers patient confirmation via `interrupt()`.
6. `cancel_appointment`: Prepares cancellation payload and triggers patient confirmation via `interrupt()`.
7. `reschedule_appointment`: Prepares rescheduling payload and triggers patient confirmation via `interrupt()`.
*Security Context:* Patient identity (`patient_id`) is injected strictly from the authenticated execution context (`RunnableConfig`), never accepted as an LLM argument.

### **R3: LangGraph Patient Booking Agent**
- Built custom `StateGraph(MessagesState)` with explicit nodes:
  - `red_flag_node`: Evaluates raw patient message before agent or tool invocation.
  - `agent_node`: Injects dynamic prompt and calls LLM bound with tools.
  - `tools` (`ToolNode`): Executes authorized tool functions.
- **Red-Flag Pre-emption:**
  - Emergency symptoms (e.g. sudden vision loss, curtain/shadow, chemical injury) trigger immediate pre-emption before the agent or tools can run.
  - An `UrgentCase` is automatically recorded with `[Chat]` origin and visible in Staff Desk.
  - Returns the exact required emergency alert text without continuing to RAG or booking.
- **Dynamic Context Builder:**
  - Injects live clinic clock (`ClockService.now()`), 30-day clinic calendar (open/Sunday/holiday breakdown), patient's upcoming visits, pending staff approvals, past visit notes, and the minor routing clause (`age < 16` routes to Paediatric Ophthalmology / Dr. Vikram Menon).

### **R4: In-Memory Conversation Memory**
- **Checkpointer:** Integrated LangGraph `InMemorySaver` with `thread_id` tracking.
- **Context Management:** Limits conversation context to at most 20 messages, trimming safely at message boundaries without stranding tool calls.
- **Privacy & Storage:** No chat history is written to the database; session memory resets completely on "New Chat" and logout.
- **Patient-Bound Thread Isolation (Safeguard 1):** In-memory thread registry binds every `thread_id` to its authenticated `patient_id`. Cross-patient access attempts immediately fail with HTTP 403 Forbidden.

### **R5: Human-in-the-Loop Confirmation Workflow**
- Uses LangGraph `interrupt()` and `Command(resume=True|False)` to pause execution and require explicit patient confirmation before committing database mutations:
  - Booking new appointments.
  - Cancelling existing appointments.
  - Rescheduling appointments.
- **Server-Side Action State (Safeguard 3):** Confirmation executes only the server-generated action stored in the LangGraph checkpoint. The client resubmits only a boolean `{ confirm: true | false }`.
- **Auto-Cancellation on New Message (Safeguard 4):** If the patient types a new message instead of pressing Confirm/Decline, the agent safely cancels/declines the pending action before executing the new request.
- **Idempotency:** Confirmations cannot execute twice. Re-confirming an executed action safely returns `"There is no pending action to confirm or decline."`

### **R6: Grounded Document Answers**
- Information queries are grounded strictly in the three clinic markdown documents (`procedures.md`, `doctors.md`, `clinic_policy_faq.md`).
- Generates answers strictly from retrieved chunks with Python-side citation validation (`File > Section`).
- Returns the fixed `"I don't know"` response when retrieved context is insufficient or ungrounded, without hallucinating doctor names or clinic policies.
- Zero medical diagnosis, treatment, or drug recommendations.

---

## 2. Architecture & File Mapping

```
                                      +-------------------------+
                                      |    POST /api/v1/chat    |
                                      +------------+------------+
                                                   |
                                       [validate_thread_ownership]
                                                   |
                                                   v
                                      +-------------------------+
                                      |     red_flag_node       |
                                      +------------+------------+
                                                   |
                          +------------------------+------------------------+
                          | (Emergency / Error)                             | (Normal)
                          v                                                 v
               +----------------------+                           +-------------------+
               |  Create UrgentCase   |                           |    agent_node     |
               |  Exact Alert -> END  |                           | (Prompt + History)|
               +----------------------+                           +---------+---------+
                                                                            |
                                                      +---------------------+---------------------+
                                                      | (Tool Calls)                              | (Direct / Answer)
                                                      v                                           v
                                            +-------------------+                               +-----+
                                            |     ToolNode      |                               | END |
                                            +---------+---------+                               +-----+
                                                      |
                                          +-----------+-----------+
                                          |                       |
                             (book / cancel / resched)      (search / list / slots)
                                          |                       |
                                          v                       +-----> Tool Result -> agent_node
                                 +------------------+
                                 |   interrupt()    |
                                 |  pending_action  |
                                 +--------+---------+
                                          |
                                   (Patient UI)
                                 Confirm / Decline
                                          |
                                          v
                                 +------------------+
                                 |  Command(resume) |
                                 | Execute Mutation |
                                 +--------+---------+
                                          |
                                          v
                                     agent_node -> END
```

### **File Inventory**

| File Path | Role | Description |
|---|---|---|
| [backend/app/services/agent.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/app/services/agent.py) | Created | LangGraph patient booking agent: `StateGraph`, `red_flag_node`, `agent_node`, prompt context builder, thread registry, `run_agent_turn`, interrupt/resume engine. |
| [backend/app/services/tools.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/app/services/tools.py) | Created | 7 LangChain agent tools (`search_clinic_docs`, `list_doctors`, `find_slots`, `my_appointments`, `book_appointment`, `cancel_appointment`, `reschedule_appointment`). |
| [backend/app/api/chat.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/app/api/chat.py) | Modified | Chat endpoint routing patient messages into `run_agent_turn` while preserving legacy RAG execution paths for Iteration 3 evaluation scripts. |
| [backend/app/schemas.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/app/schemas.py) | Modified | Pydantic models for `ChatRequest` (`thread_id`, `confirm`), `ChatResponse` (`pending_action`, `thread_id`), rescheduling schemas, and staff review schemas. |
| [backend/app/models.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/app/models.py) | Modified | Added appointment statuses (`pending_cancellation`, `pending_rescheduling`) and `StaffApproval` tracking model. |
| [backend/app/api/appointments.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/app/api/appointments.py) | Modified | Atomic rescheduling endpoint and 2-hour cancellation/rescheduling boundary logic. |
| [backend/app/api/staff.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/app/api/staff.py) | Modified | Staff approval/rejection endpoints with `ClinicRulesEngine` re-validation. |
| [frontend/src/api.js](file:///c:/Users/sindhu/Desktop/NetraCare/frontend/src/api.js) | Modified | Added `confirmChatAction(threadId, confirm)` and updated `sendChatMessage` to pass `threadId`. |
| [frontend/src/components/PatientChat.jsx](file:///c:/Users/sindhu/Desktop/NetraCare/frontend/src/components/PatientChat.jsx) | Modified | Session thread management, "New Chat" reset, interactive confirmation card (`pending_action`), auto-clearing unconfirmed actions on new input. |
| [frontend/src/components/PatientPortal.jsx](file:///c:/Users/sindhu/Desktop/NetraCare/frontend/src/components/PatientPortal.jsx) | Modified | Connected `onAppointmentChange` callback to automatically refresh appointment list when actions confirm. |
| [frontend/src/components/StaffDesk.jsx](file:///c:/Users/sindhu/Desktop/NetraCare/frontend/src/components/StaffDesk.jsx) | Modified | Added Pending Approvals queue tab with Approve and Reject actions. |
| [backend/tests/verify_iteration_4_final.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/tests/verify_iteration_4_final.py) | Created | Standalone verification script executing all 24 agent scenarios and security/safeguard checks. |

---

## 3. Database Configuration

- **Database Engine:** SQLite (Primary active runtime)
- **Database URL:** `sqlite:///./netracare.db`
- **Fallback Setting:** `AUTO_FALLBACK_TO_SQLITE=true`
- **Schema Modifications:**
  - `appointments.status`: added values `'pending_cancellation'` and `'pending_rescheduling'`.
  - `staff_approvals` table: stores pending patient requests inside 2 hours (`appointment_id`, `patient_id`, `action_type`, `new_doctor_id`, `new_date`, `new_start_time`, `new_end_time`, `status`, `reason`).
- **Data Integrity:** All original seed data and Iteration 2 past visits (62 total appointments) are intact. Zero table drops or data destruction occurred.

---

## 4. Test Results

### **Summary Table**

| Test Suite / Runner | Target Feature / Verification Scope | Tests Run | Result |
|---|---|---|---|
| [test_rules.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/tests/test_rules.py) | ClinicRulesEngine: slot validity, booking constraints, double-booking prevention | 38 | **38 Passed** |
| [test_iteration_2.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/tests/test_iteration_2.py) | Iteration 2: Clinical notes, red-flags, past visits, patient profiles | 10 | **10 Passed** |
| [test_iteration_3.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/tests/test_iteration_3.py) | Iteration 3: Hybrid retrieval, citation validation, grounded RAG answers | 9 | **9 Passed** |
| [test_iteration_4_r1.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/tests/test_iteration_4_r1.py) | Iteration 4 R1: Atomic rescheduling & staff review approval queues | 7 | **7 Passed** |
| [test_iteration_4_r2.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/tests/test_iteration_4_r2.py) | Iteration 4 R2: 7 agent tools with rules engine validation | 9 | **9 Passed** |
| [test_iteration_4_agent.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/tests/test_iteration_4_agent.py) | Iteration 4 R3–R6: LangGraph graph, context prompt, interrupts, isolation | 10 | **10 Passed** |
| [verify_iteration_4_final.py](file:///c:/Users/sindhu/Desktop/NetraCare/backend/tests/verify_iteration_4_final.py) | AS01–AS24 Scenarios + Thread Security & Idempotency Safeguards | 28 | **28 Passed** |
| **Total Test Suite** | **Comprehensive Full System Verification** | **111** | **111 Passed (100%)** |
| **Frontend Production Build** | `npm run build --prefix frontend` (Vite + TypeScript) | — | **Success (5.44s)** |

### **Agent Scenarios Verification (AS01–AS24)**
All 24 scenarios from `agent_scenarios.csv` passed on the fixed clinic clock `2026-11-02 10:00`:
- **Bookings (8):** AS01, AS02, AS03, AS10, AS11, AS12, AS15, AS17 -> Correct doctor, speciality, duration, and slot booked.
- **Reschedules (2):** AS05, AS21 -> Correctly updated in database upon confirmation.
- **Cancellations (2):** AS06 (to Staff approval, `< 2h`), AS07 (cancelled, `> 2h`).
- **Safely Declined / No-Change (8):** AS04 (`ACTIVE_BOOKING_EXISTS`), AS08 (declined by patient), AS09 (`NOT_YOUR_APPOINTMENT`), AS16 (`BEYOND_30_DAYS`), AS18 (`OUTSIDE_SESSION`), AS19 (`DOUBLE_BOOKED`), AS20 (`DOCTOR_OFF`), AS22 (`SURGERY_SESSION`).
- **Emergency Interceptions (2):** AS13 (curtain symptom), AS14 (chemical cleaner) -> Immediate `UrgentCase` with `[Chat]` origin; exact emergency message returned.
- **Appointments Query (1):** AS23 -> Accurately returned patient's own upcoming appointment.
- **Clinic Document Fallback (1):** AS24 -> Exact fixed `"I don't know"` response for parking inquiry.

---

## 5. Known Limitations & Operational Considerations

1. **Gemini Free Tier Daily Quota:**
   - The configured free-tier Gemini API key has a hard limit of 20 requests/day (`RESOURCE_EXHAUSTED 429`).
   - Automated test suites mock `LLMService.get_model` and `LLMService.check_red_flags` for fast, deterministic verification without exhausting API quota.
   - For live end-to-end multi-turn testing in the UI, an API key with adequate quota is required.
2. **In-Memory Thread Persistence:**
   - Conversation threads and LangGraph checkpoints reside in `InMemorySaver`.
   - Server restarts reset active conversation memory and pending interrupt states, as per R4 specifications ("Do not persist chat history in database").
3. **Excluded Scope (R7):**
   - Requirement R7 (Doctor Leave management and Staff automated rebooking) was explicitly excluded from Iteration 4 and is not implemented.

---

## 6. Current Deployment & Runtime Configuration

### **Backend**
```powershell
$env:DATABASE_URL="sqlite:///./netracare.db"
$env:PYTHONPATH="backend"
python backend/app/main.py
```
- Listens on `http://localhost:8000`.
- API endpoints active:
  - `POST /api/v1/chat` — Patient LangGraph booking assistant.
  - `POST /api/v1/appointments/{id}/reschedule` — Atomic rescheduling.
  - `POST /api/v1/appointments/{id}/cancel` — Cancellation with 2h staff boundary.
  - `GET /api/v1/staff/pending-approvals` — Pending staff queue.
  - `POST /api/v1/staff/approvals/{id}/approve` — Staff approval execution.
  - `POST /api/v1/staff/approvals/{id}/reject` — Staff rejection execution.

### **Frontend**
```powershell
npm run dev --prefix frontend
```
- Listens on `http://localhost:5173`.
- Production build verified: `npm run build --prefix frontend` succeeds with zero errors (`dist/assets/index-BQtgADD6.js` 298.12 kB).
