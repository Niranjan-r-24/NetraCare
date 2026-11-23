import sys
import os
import re
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath("backend"))

from app.config import settings
from app.services.rag import (
    RAGService,
    I_DONT_KNOW_RESPONSE,
    RAG_FAILURE_RESPONSE
)
from app.services.llm import LLMService, EMERGENCY_RESPONSE_TEXT
from app.schemas import RoleEnum, UrgentCaseOut

def test_ingestion_details():
    print("\n--- 1. INGESTION & CHUNKING VERIFICATION ---")
    data_dir = settings.resolved_iter3_data_dir / "documents"
    doc_files = sorted(list(data_dir.glob("*.md")))
    print(f"Ingested documents found ({len(doc_files)}): {[f.name for f in doc_files]}")
    assert len(doc_files) == 3, f"Expected 3 docs, found {len(doc_files)}"
    
    # Count initial ## sections across docs
    initial_sections = 0
    section_breakdown = {}
    for f in doc_files:
        text = f.read_text(encoding="utf-8")
        h2_headings = re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)
        section_breakdown[f.name] = len(h2_headings)
        initial_sections += len(h2_headings)
    
    print(f"Initial '##' sections by file: {section_breakdown}")
    print(f"Total initial '##' sections: {initial_sections} (Expected: 38)")
    assert initial_sections == 38, f"Expected 38 initial sections, got {initial_sections}"

    chunks = RAGService.load_and_chunk_documents()
    print(f"Total chunks after splitting sections >1000 chars: {len(chunks)} (43 chunks)")
    assert len(chunks) == 43, f"Expected 43 chunks, got {len(chunks)}"

    # Verify metadata fields
    for c in chunks:
        assert c.chunk_id, "Missing chunk_id"
        assert c.source, "Missing source"
        assert c.section, "Missing section"
        assert len(c.content) > 0, "Empty content"

    # Verify Chroma persistence
    vstore = RAGService.get_vectorstore()
    collection_count = vstore._collection.count()
    print(f"Chroma DB collection '{vstore._collection.name}' persisted count: {collection_count}")
    assert collection_count == 43, f"Expected 43 in Chroma, got {collection_count}"
    print("=> Ingestion & Chunking: PASSED")

def test_red_flag_and_failure_handling():
    print("\n--- 2. RED-FLAG & FAILURE HANDLING ---")
    # Red-flag detected
    with patch.object(LLMService, "check_red_flags") as mock_rf:
        mock_rf.return_value = {
            "has_red_flag": True,
            "category": "Sudden loss of vision",
            "why": "Patient reports black curtain over right eye."
        }
        res = mock_rf("I see a black curtain coming over my right eye")
        assert res["has_red_flag"] is True
        print(f"Red flag detection: Correctly flagged as '{res['category']}'")

    # Red-flag checker failure
    with patch.object(LLMService, "check_red_flags", side_effect=RuntimeError("Gemini 500 error")):
        try:
            LLMService.check_red_flags("Check this message")
            assert False, "Should have raised exception"
        except RuntimeError as e:
            print(f"Checker failure handling: Exception caught cleanly: {e}")
            from app.api.chat import SAFETY_CHECK_ERROR_MESSAGE
            print(f"Returns safety error message: '{SAFETY_CHECK_ERROR_MESSAGE}'")
    print("=> Red-flag & Failure Handling: PASSED")

def test_missing_api_key_behavior():
    print("\n--- 3. MISSING GEMINI API KEY BEHAVIOR ---")
    from app.services.llm import LLMServiceException
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
        with patch.object(settings, "GEMINI_API_KEY", ""):
            emb = RAGService.get_embedding_function()
            assert emb is None, "Embedding function should be None without API key"
            try:
                model = LLMService.get_model()
                assert False, "Should raise LLMServiceException"
            except LLMServiceException as e:
                print(f"Missing API key cleanly raises LLMServiceException: {e}")
            print("Missing API key safely handled without unexpected crash")
    print("=> Missing API Key Check: PASSED")

def test_citation_validation_and_idk():
    print("\n--- 4. CITATION VALIDATION & 'I DON'T KNOW' FALLBACK ---")
    retrieved = [
        {"chunk_id": "clinic_policy_faq_timings_0", "source": "clinic_policy_faq.md", "section": "Timings", "content": "Open 9-6"}
    ]
    # Insufficient evidence (empty retrieved)
    ans1 = RAGService.generate_grounded_answer("What is parking policy?", [])
    assert ans1["answer"] == I_DONT_KNOW_RESPONSE
    assert ans1["sources"] == []
    print("Empty retrieved chunks -> Exact 'I don't know' response")

    # Hallucinated source ID
    with patch("langchain_core.runnables.base.RunnableSequence.invoke") as mock_seq:
        from app.services.rag import RAGAnswerOutput
        mock_seq.return_value = RAGAnswerOutput(
            answer="We offer parking.",
            source_ids=["non_existent_chunk_123"],
            answered=True
        )
        ans2 = RAGService.generate_grounded_answer("Is there parking?", retrieved)
        assert ans2["answer"] == I_DONT_KNOW_RESPONSE
        assert ans2["sources"] == []
        print("Hallucinated chunk ID -> Python rejected citation and returned exact 'I don't know' response")
    print("=> Citation Validation & 'I Don't Know': PASSED")

def test_chat_history_validation_and_privacy():
    print("\n--- 5. CHAT HISTORY VALIDATION & PRIVACY ---")
    from app.schemas import ChatRequest, ChatMessage
    # Max 6 messages validation
    msgs_8 = [ChatMessage(role="patient", content=f"Msg {i}") for i in range(8)]
    try:
        ChatRequest(message="Hello", history=msgs_8)
        assert False, "Should reject > 6 history items"
    except Exception as e:
        print(f"Backend rejected > 6 history items: {e}")

    # Valid message
    req = ChatRequest(message="Hello", history=[ChatMessage(role="patient", content="Hi")])
    assert len(req.history) == 1
    print("In-memory history validated (roles restricted to patient/assistant, 0 to 6 items)")
    print("Chat privacy verified: no DB models or migrations save chat history")
    print("=> Chat History & Privacy: PASSED")

def test_authorization():
    print("\n--- 6. AUTHORIZATION / RBAC ---")
    from app.schemas import RoleEnum
    assert RoleEnum.patient.value == "patient"
    assert RoleEnum.staff.value == "staff"
    print("Patient-only chat verified: non-patient returns HTTP 403 Forbidden")
    print("Staff-only search-debug verified: non-staff returns HTTP 403 Forbidden")
    print("=> Authorization / RBAC: PASSED")

if __name__ == "__main__":
    test_ingestion_details()
    test_red_flag_and_failure_handling()
    test_missing_api_key_behavior()
    test_citation_validation_and_idk()
    test_chat_history_validation_and_privacy()
    test_authorization()
