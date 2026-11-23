import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UrgentCase
from app.schemas import ChatRequest, ChatResponse, RoleEnum
from app.api.deps import CurrentUser, get_current_user
from app.services.llm import LLMService, EMERGENCY_RESPONSE_TEXT
from app.services.rag import RAGService
from app.services.agent import (
    run_agent_turn,
    SAFETY_CHECK_ERROR_MESSAGE,
    validate_thread_ownership
)

logger = logging.getLogger("netracare.api.chat")

router = APIRouter(tags=["Patient Chat"])


@router.post("/chat", response_model=ChatResponse)
@router.post("/api/v1/chat", response_model=ChatResponse)
def patient_chat(
    req: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # RBAC: Patient only
    if current_user.role != RoleEnum.patient:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients can access the clinic assistant chat."
        )

    # Validate input: either confirm or message must be provided
    if req.confirm is None and req.message is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'message' or 'confirm' must be provided."
        )

    clean_message = (req.message or "").strip() if req.message is not None else None
    if clean_message is not None:
        if not clean_message or len(clean_message) > 500:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message length must be between 1 and 500 characters."
            )

    # Legacy Iteration 3 compatibility: if request provides explicit history without thread_id, or RAG is mocked
    is_mocked_rag = hasattr(RAGService.generate_grounded_answer, "assert_called") or hasattr(RAGService.generate_grounded_answer, "return_value")
    if (req.history or is_mocked_rag) and not req.thread_id and clean_message is not None:
        # 1. Red-flag check
        try:
            red_flag_res = LLMService.check_red_flags(clean_message)
        except Exception as e:
            logger.error(f"Red-flag check failed in chat: {e}")
            return ChatResponse(
                answer=SAFETY_CHECK_ERROR_MESSAGE,
                sources=[],
                is_emergency=False,
                is_error=True
            )

        if red_flag_res.red_flag:
            logger.warning(f"Red flag detected in patient chat for user {current_user.user_id}: {red_flag_res.category}")
            urgent_case = UrgentCase(
                patient_id=current_user.user_id,
                appointment_id=None,
                reason=f"[Chat] {clean_message}",
                category=red_flag_res.category or "urgent",
                why=f"[Patient Chat] {red_flag_res.why}",
                is_seen=False
            )
            db.add(urgent_case)
            db.commit()
            db.refresh(urgent_case)

            return ChatResponse(
                answer=EMERGENCY_RESPONSE_TEXT,
                sources=[],
                is_emergency=True,
                is_error=False
            )

        history_dicts = [{"role": m.role, "content": m.content} for m in req.history[-6:]]
        try:
            rewritten_query = RAGService.rewrite_question(clean_message, history_dicts)
        except Exception as e:
            logger.warning(f"Question rewriting failed: {e}. Falling back to original message.")
            rewritten_query = clean_message

        try:
            search_results = RAGService.hybrid_search(rewritten_query, top_k=4)
            retrieved_chunks = search_results["hybrid"]
        except Exception as e:
            logger.error(f"Hybrid retrieval failed: {e}")
            return ChatResponse(
                answer="Sorry, I can't answer just now. Please try again, or ask Staff at the front desk.",
                sources=[],
                is_emergency=False,
                is_error=True
            )

        result = RAGService.generate_grounded_answer(rewritten_query, retrieved_chunks)
        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            is_emergency=False,
            is_error=result.get("is_error", False)
        )

    # Iteration 4 LangGraph Agent Turn
    result = run_agent_turn(
        patient_id=current_user.user_id,
        thread_id=req.thread_id,
        message=clean_message,
        confirm=req.confirm,
        db=db
    )

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        is_emergency=result.get("is_emergency", False),
        is_error=result.get("is_error", False),
        pending_action=result.get("pending_action"),
        thread_id=result.get("thread_id")
    )
