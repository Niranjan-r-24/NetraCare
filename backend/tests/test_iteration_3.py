import os
import sys
import pytest
from datetime import datetime, date, time
from unittest.mock import patch, MagicMock

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, Base, engine, ensure_schema_updates
from app.models import Patient, Appointment, Doctor, UrgentCase
from app.seeder import seed_database
from app.services.llm import LLMService, RedFlagOutput, EMERGENCY_RESPONSE_TEXT
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from app.services.rag import (
    RAGService, I_DONT_KNOW_RESPONSE, RAG_FAILURE_RESPONSE, RAGAnswerOutput
)

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    ensure_schema_updates(engine)
    db = SessionLocal()
    db.query(UrgentCase).delete()
    db.commit()
    seed_database(db, seed_appointments=True)
    db.close()
    yield

def patient_auth(p_id="P01", name="Asha Verma"):
    return {"X-Role": "patient", "X-User-Id": p_id, "X-User-Name": name}

def doctor_auth(d_id="D3", name="Dr. Shah"):
    return {"X-Role": "doctor", "X-User-Id": d_id, "X-User-Name": name}

staff_auth = {"X-Role": "staff", "X-User-Id": "STAFF_01", "X-User-Name": "Receptionist"}

# ============================================================================
# R1 Tests: Knowledge-base Ingestion & Section Chunking
# ============================================================================
def test_r1_knowledge_base_chunks_and_metadata():
    chunks = RAGService.get_chunks()
    assert len(chunks) >= 38, f"Expected at least 38 chunks, got {len(chunks)}"
    
    # Verify metadata fields
    sources = set()
    sections = set()
    for c in chunks:
        assert c.chunk_id, "Every chunk must have a non-empty chunk_id"
        assert c.source.endswith(".md"), f"Chunk source must end with .md: {c.source}"
        assert c.section, f"Chunk section heading must be present: {c.chunk_id}"
        assert len(c.content) > 10, f"Chunk content must not be empty: {c.chunk_id}"
        sources.add(c.source)
        sections.add(c.section)

    assert "clinic_policy_faq.md" in sources
    assert "doctors.md" in sources
    assert "procedures.md" in sources
    assert len(sections) >= 38, f"Expected at least 38 distinct sections, got {len(sections)}"

# ============================================================================
# R2 Tests: Hybrid Retrieval & Staff Search-Debug Interface
# ============================================================================
def test_r2_hybrid_retrieval_specified_examples():
    # 1. Query 1: HbA1c report -> BM25 top 1 is Diabetic eye check, hybrid in top 4
    res1 = RAGService.hybrid_search("Should I bring my HbA1c report?", top_k=4)
    assert len(res1["keyword_only"]) > 0
    assert "Diabetic eye check" in res1["keyword_only"][0]["section"], "Keyword search should rank Diabetic eye check first"
    assert any("Diabetic eye check" in c["section"] for c in res1["hybrid"]), "Hybrid search should include Diabetic eye check in top 4"

    # 2. Query 2: operation to straighten eye -> Vector finds Squint surgery, hybrid in top 4
    res2 = RAGService.hybrid_search("Can my kid have breakfast on the morning of the operation to straighten his eye?", top_k=4)
    assert any("Squint surgery" in c["section"] for c in res2["vector_only"]), "Vector search should find Squint surgery in top 4"
    assert any("Squint surgery" in c["section"] for c in res2["hybrid"]), "Hybrid search should include Squint surgery in top 4"

def test_r2_search_debug_rbac():
    # Non-staff role gets 403 Forbidden
    res_pat = client.get("/api/v1/staff/search-debug?q=cataract", headers=patient_auth())
    assert res_pat.status_code == 403

    res_doc = client.get("/api/v1/staff/search-debug?q=cataract", headers=doctor_auth())
    assert res_doc.status_code == 403

    # Unauthenticated gets 401
    res_unauth = client.get("/api/v1/staff/search-debug?q=cataract")
    assert res_unauth.status_code == 401

    # Staff gets 200 with keyword, vector, hybrid columns
    res_staff = client.get("/api/v1/staff/search-debug?q=cataract", headers=staff_auth)
    assert res_staff.status_code == 200
    data = res_staff.json()
    assert "keyword_only" in data and len(data["keyword_only"]) <= 4
    assert "vector_only" in data and len(data["vector_only"]) <= 4
    assert "hybrid" in data and len(data["hybrid"]) <= 4

# ============================================================================
# R3 Tests: Patient-Only Chat Endpoint & History Validation
# ============================================================================
def test_r3_chat_endpoint_rbac_and_input_limits():
    # 1. Non-patient gets 403
    res_staff = client.post("/api/v1/chat", headers=staff_auth, json={"message": "Hello"})
    assert res_staff.status_code == 403

    res_doc = client.post("/api/v1/chat", headers=doctor_auth(), json={"message": "Hello"})
    assert res_doc.status_code == 403

    # 2. Message length > 500 characters rejected (400 or 422)
    long_msg = "A" * 505
    res_long = client.post("/api/v1/chat", headers=patient_auth(), json={"message": long_msg})
    assert res_long.status_code in (400, 422)

    # 3. Empty message rejected
    res_empty = client.post("/api/v1/chat", headers=patient_auth(), json={"message": "   "})
    assert res_empty.status_code in (400, 422)

@patch.object(LLMService, "check_red_flags")
@patch.object(RAGService, "rewrite_question")
@patch.object(RAGService, "generate_grounded_answer")
def test_r3_question_rewriting_called_with_history(mock_answer, mock_rewrite, mock_red_flag):
    mock_red_flag.return_value = RedFlagOutput(red_flag=False, category=None, why="Routine follow-up inquiry")
    mock_rewrite.return_value = "What should I avoid after cataract surgery?"
    mock_answer.return_value = {
        "answer": "Avoid rubbing the eye, getting soap in it for a week, and swimming for 4 weeks.",
        "sources": ["procedures.md › Cataract surgery"],
        "is_error": False
    }

    history = [
        {"role": "patient", "content": "How much does cataract surgery cost?"},
        {"role": "assistant", "content": "It costs ₹35,000 to ₹90,000 per eye, indicative."}
    ]

    res = client.post(
        "/api/v1/chat",
        headers=patient_auth(),
        json={
            "message": "What should I avoid after it?",
            "history": history
        }
    )
    assert res.status_code == 200
    mock_rewrite.assert_called_once()
    args, _ = mock_rewrite.call_args
    assert args[0] == "What should I avoid after it?"
    assert len(args[1]) == 2
    assert args[1][0]["content"] == "How much does cataract surgery cost?"

# ============================================================================
# R4 Tests: Red-Flag Check Before RAG & Urgent Case Persistence
# ============================================================================
@patch.object(LLMService, "check_red_flags")
def test_r4_red_flag_triggers_emergency_and_stops_rag(mock_red_flag):
    mock_red_flag.return_value = RedFlagOutput(
        red_flag=True,
        category="curtain_or_shadow",
        why="A curtain coming down over eye is a sign of retinal detachment"
    )

    db = SessionLocal()
    # Delete prior urgent cases for P01
    db.query(UrgentCase).filter(UrgentCase.patient_id == "P01").delete()
    db.commit()
    db.close()

    res = client.post(
        "/api/v1/chat",
        headers=patient_auth("P01"),
        json={"message": "A curtain came down over my left eye an hour ago"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_emergency"] is True
    assert data["answer"] == EMERGENCY_RESPONSE_TEXT
    assert data["sources"] == []

    # Check database: UrgentCase created with appointment_id=None and [Chat] prefix
    db = SessionLocal()
    try:
        uc = db.query(UrgentCase).filter(UrgentCase.patient_id == "P01", UrgentCase.is_seen == False).first()
        assert uc is not None
        assert uc.appointment_id is None
        assert uc.reason.startswith("[Chat]")
        assert uc.category == "curtain_or_shadow"
    finally:
        db.close()

@patch.object(LLMService, "check_red_flags")
def test_r4_red_flag_failure_stops_chat(mock_red_flag):
    mock_red_flag.side_effect = Exception("API connection timed out")

    res = client.post(
        "/api/v1/chat",
        headers=patient_auth("P01"),
        json={"message": "What time does the clinic open?"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_error"] is True
    assert "We couldn't check your message just now" in data["answer"]
    assert data["sources"] == []

# ============================================================================
# R5 Tests: Grounded Answers, Citation Validation & "I don't know"
# ============================================================================
def test_r5_citation_validation_in_code():
    # Simulated retrieved chunks
    sample_chunks = [
        {"chunk_id": "clinic_policy_faq_timings_0", "source": "clinic_policy_faq.md", "section": "Timings", "content": "Open Mon-Sat 9am-6pm"}
    ]

    # 1. Valid citation matching retrieved chunk
    with patch.object(LLMService, "get_model") as mock_get_model:
        mock_get_model.return_value = RunnableLambda(
            lambda x: AIMessage(
                content='{"answer": "NetraCare is open Monday to Saturday from 9 AM to 6 PM.", "source_ids": ["clinic_policy_faq_timings_0"], "answered": true}'
            )
        )

        res = RAGService.generate_grounded_answer("When are you open?", sample_chunks)
        assert res["answer"] == "NetraCare is open Monday to Saturday from 9 AM to 6 PM."
        assert res["sources"] == ["clinic_policy_faq.md › Timings"]

    # 2. Hallucinated chunk ID not in retrieved chunks -> Must return exact I_DONT_KNOW_RESPONSE
    with patch.object(LLMService, "get_model") as mock_get_model:
        mock_get_model.return_value = RunnableLambda(
            lambda x: AIMessage(
                content='{"answer": "There is valet parking behind the clinic.", "source_ids": ["non_existent_parking_chunk_99"], "answered": true}'
            )
        )

        res_idk = RAGService.generate_grounded_answer("Is there parking?", sample_chunks)
        assert res_idk["answer"] == I_DONT_KNOW_RESPONSE
        assert res_idk["sources"] == []

    # 3. answered=False -> Must return exact I_DONT_KNOW_RESPONSE
    with patch.object(LLMService, "get_model") as mock_get_model:
        mock_get_model.return_value = RunnableLambda(
            lambda x: AIMessage(
                content='{"answer": "I do not see that info.", "source_ids": [], "answered": false}'
            )
        )

        res_unanswered = RAGService.generate_grounded_answer("Can I pay by crypto?", sample_chunks)
        assert res_unanswered["answer"] == I_DONT_KNOW_RESPONSE
        assert res_unanswered["sources"] == []

# ============================================================================
# R6 Tests: Speciality Routing & Doctor Attribution
# ============================================================================
@patch.object(LLMService, "check_red_flags")
@patch.object(RAGService, "generate_grounded_answer")
def test_r6_speciality_routing_names_doctors_no_diagnosis(mock_ans, mock_red_flag):
    mock_red_flag.return_value = RedFlagOutput(red_flag=False, category=None, why="Non-urgent high eye pressure query")
    mock_ans.return_value = {
        "answer": "A Glaucoma specialist can assess this. At NetraCare that is Dr. Meera Iyer. The doctor will assess you at your visit.",
        "sources": ["doctors.md › Glaucoma"],
        "is_error": False
    }

    res = client.post(
        "/api/v1/chat",
        headers=patient_auth(),
        json={"message": "My optician said the pressure in my eyes is high"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "Glaucoma" in data["answer"]
    assert "Dr. Meera Iyer" in data["answer"]
    assert "procedures" not in data["sources"][0]
    # Ensure no diagnosis was given
    assert "you have glaucoma" not in data["answer"].lower()
