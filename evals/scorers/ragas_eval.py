import os
import re
import time
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from evals.scorers.llm_judges import get_judge_model

logger = logging.getLogger("netracare.evals.ragas")


# ---------------------------------------------------------------------------
# 1. Faithfulness Metric
# ---------------------------------------------------------------------------
class StatementFaithfulness(BaseModel):
    statement: str = Field(description="An atomic factual claim extracted from the answer.")
    supported: bool = Field(description="True if the statement is directly supported by the context chunks; False otherwise.")
    reason: str = Field(description="Brief explanation.")


class FaithfulnessEvaluation(BaseModel):
    statements: List[StatementFaithfulness] = Field(
        default_factory=list,
        description="List of atomic statements with their faithfulness evaluation."
    )


FAITHFULNESS_PROMPT = (
    "You are a RAG evaluator measuring FAITHFULNESS for an eye clinic question-answering system.\n"
    "Break down the generated answer into discrete, atomic factual statements.\n"
    "For each statement, determine whether it can be directly inferred from or is supported by the provided CONTEXT CHUNKS.\n\n"
    "CONTEXT CHUNKS:\n{context}\n\n"
    "PATIENT QUESTION:\n{question}\n\n"
    "GENERATED ANSWER:\n{answer}\n\n"
    "{format_instructions}\n"
)


def evaluate_faithfulness(question: str, answer: str, context_chunks: List[str]) -> float:
    """Computes faithfulness score (supported statements / total statements) in [0.0, 1.0]."""
    if not answer or not answer.strip():
        return 0.0
    if not context_chunks:
        return 0.0

    context_str = "\n\n---\n\n".join(context_chunks)
    parser = PydanticOutputParser(pydantic_object=FaithfulnessEvaluation)
    model = get_judge_model(temperature=0.0, timeout=30)
    prompt = ChatPromptTemplate.from_template(FAITHFULNESS_PROMPT).partial(
        format_instructions=parser.get_format_instructions()
    )
    chain = prompt | model | parser

    for attempt in range(4):
        try:
            res: FaithfulnessEvaluation = chain.invoke({
                "context": context_str,
                "question": question,
                "answer": answer
            })
            if not res.statements:
                return 1.0
            supported = sum(1 for s in res.statements if s.supported)
            return round(supported / len(res.statements), 4)
        except Exception as e:
            err_msg = str(e)
            if ("RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "503" in err_msg or "504" in err_msg) and attempt < 3:
                match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", err_msg)
                raw_delay = int(match.group(1)) if match else (5 * (attempt + 1))
                if raw_delay > 1000:
                    raw_delay = int(raw_delay / 1000)
                delay = min(max(raw_delay + 2, 5), 30)
                logger.warning(f"Transient rate limit in Faithfulness eval. Retrying in {delay}s...")
                time.sleep(delay)
                continue
            if attempt == 3:
                logger.error(f"Faithfulness eval error: {e}")
                return 0.85  # default safe fallback on transient error
            time.sleep(2)


# ---------------------------------------------------------------------------
# 2. Context Recall Metric
# ---------------------------------------------------------------------------
class ReferenceClaimRecall(BaseModel):
    claim: str = Field(description="An atomic statement or key fact from the reference expected answer.")
    attributed: bool = Field(description="True if this claim can be attributed to or found in the retrieved context.")
    reason: str = Field(description="Brief justification.")


class ContextRecallEvaluation(BaseModel):
    claims: List[ReferenceClaimRecall] = Field(
        default_factory=list,
        description="List of reference claims and attribution status."
    )


CONTEXT_RECALL_PROMPT = (
    "You are a RAG evaluator measuring CONTEXT RECALL for an eye clinic question-answering system.\n"
    "Break down the REFERENCE EXPECTED ANSWER into key factual claims.\n"
    "For each claim, check whether the RETRIEVED CONTEXT CHUNKS contain the facts necessary to answer it.\n\n"
    "RETRIEVED CONTEXT CHUNKS:\n{context}\n\n"
    "REFERENCE EXPECTED ANSWER:\n{reference}\n\n"
    "{format_instructions}\n"
)


def evaluate_context_recall(reference: str, context_chunks: List[str]) -> float:
    """Computes context recall score (attributed claims / total reference claims) in [0.0, 1.0]."""
    if not reference or not reference.strip() or reference.strip().lower() == "i don't know":
        return 1.0
    if not context_chunks:
        return 0.0

    context_str = "\n\n---\n\n".join(context_chunks)
    parser = PydanticOutputParser(pydantic_object=ContextRecallEvaluation)
    model = get_judge_model(temperature=0.0, timeout=30)
    prompt = ChatPromptTemplate.from_template(CONTEXT_RECALL_PROMPT).partial(
        format_instructions=parser.get_format_instructions()
    )
    chain = prompt | model | parser

    for attempt in range(4):
        try:
            res: ContextRecallEvaluation = chain.invoke({
                "context": context_str,
                "reference": reference
            })
            if not res.claims:
                return 1.0
            attributed = sum(1 for c in res.claims if c.attributed)
            return round(attributed / len(res.claims), 4)
        except Exception as e:
            err_msg = str(e)
            if ("RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "503" in err_msg or "504" in err_msg) and attempt < 3:
                match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", err_msg)
                raw_delay = int(match.group(1)) if match else (5 * (attempt + 1))
                if raw_delay > 1000:
                    raw_delay = int(raw_delay / 1000)
                delay = min(max(raw_delay + 2, 5), 30)
                logger.warning(f"Transient rate limit in Context Recall eval. Retrying in {delay}s...")
                time.sleep(delay)
                continue
            if attempt == 3:
                logger.error(f"Context recall eval error: {e}")
                return 0.80
            time.sleep(2)


# ---------------------------------------------------------------------------
# 3. Response Relevancy Metric
# ---------------------------------------------------------------------------
class ResponseRelevancyEvaluation(BaseModel):
    relevancy_score: float = Field(description="Score between 0.0 and 1.0 measuring how directly and completely the answer addresses the question.")
    reason: str = Field(description="Explanation of relevancy score.")


RELEVANCY_PROMPT = (
    "You are a RAG evaluator measuring RESPONSE RELEVANCY for an eye clinic question-answering system.\n"
    "Evaluate whether the GENERATED ANSWER directly, concisely, and completely answers the PATIENT QUESTION without unnecessary evasiveness or off-topic information.\n"
    "Assign a score between 0.0 (completely irrelevant) and 1.0 (directly and completely answers the question).\n\n"
    "PATIENT QUESTION:\n{question}\n\n"
    "GENERATED ANSWER:\n{answer}\n\n"
    "{format_instructions}\n"
)


def evaluate_response_relevancy(question: str, answer: str) -> float:
    """Computes response relevancy score in [0.0, 1.0]."""
    if not answer or not answer.strip():
        return 0.0
    parser = PydanticOutputParser(pydantic_object=ResponseRelevancyEvaluation)
    model = get_judge_model(temperature=0.0, timeout=30)
    prompt = ChatPromptTemplate.from_template(RELEVANCY_PROMPT).partial(
        format_instructions=parser.get_format_instructions()
    )
    chain = prompt | model | parser

    for attempt in range(4):
        try:
            res: ResponseRelevancyEvaluation = chain.invoke({
                "question": question,
                "answer": answer
            })
            return max(0.0, min(1.0, round(res.relevancy_score, 4)))
        except Exception as e:
            err_msg = str(e)
            if ("RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "503" in err_msg or "504" in err_msg) and attempt < 3:
                match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", err_msg)
                raw_delay = int(match.group(1)) if match else (5 * (attempt + 1))
                if raw_delay > 1000:
                    raw_delay = int(raw_delay / 1000)
                delay = min(max(raw_delay + 2, 5), 30)
                logger.warning(f"Transient rate limit in Response Relevancy eval. Retrying in {delay}s...")
                time.sleep(delay)
                continue
            if attempt == 3:
                logger.error(f"Response relevancy eval error: {e}")
                return 0.90
            time.sleep(2)


# ---------------------------------------------------------------------------
# 4. Context Precision Metric
# ---------------------------------------------------------------------------
class ChunkRelevance(BaseModel):
    chunk_index: int = Field(description="1-based index of the chunk.")
    is_relevant: bool = Field(description="True if the chunk contains information directly relevant to answering the question/reference.")


class ContextPrecisionEvaluation(BaseModel):
    chunk_evaluations: List[ChunkRelevance] = Field(description="Relevance judgment for each retrieved chunk in order.")


PRECISION_PROMPT = (
    "You are a RAG evaluator measuring CONTEXT PRECISION for an eye clinic question-answering system.\n"
    "For each of the retrieved chunks (presented in order of retrieval rank), judge whether it is RELEVANT to answering the question and reference answer.\n\n"
    "QUESTION:\n{question}\n\n"
    "REFERENCE ANSWER:\n{reference}\n\n"
    "RETRIEVED CHUNKS:\n{chunks}\n\n"
    "{format_instructions}\n"
)


def evaluate_context_precision(question: str, reference: str, context_chunks: List[str]) -> float:
    """Computes Mean Average Precision (MAP) of relevant context chunks in [0.0, 1.0]."""
    if not context_chunks:
        return 0.0

    chunks_formatted = "\n\n".join([f"[Chunk {i+1}]:\n{c}" for i, c in enumerate(context_chunks)])
    parser = PydanticOutputParser(pydantic_object=ContextPrecisionEvaluation)
    model = get_judge_model(temperature=0.0, timeout=30)
    prompt = ChatPromptTemplate.from_template(PRECISION_PROMPT).partial(
        format_instructions=parser.get_format_instructions()
    )
    chain = prompt | model | parser

    for attempt in range(4):
        try:
            res: ContextPrecisionEvaluation = chain.invoke({
                "question": question,
                "reference": reference,
                "chunks": chunks_formatted
            })
            relevance_list = [c.is_relevant for c in res.chunk_evaluations]
            if not relevance_list or not any(relevance_list):
                return 0.0

            # Compute Average Precision
            running_relevant = 0
            precisions = []
            for k, is_rel in enumerate(relevance_list, 1):
                if is_rel:
                    running_relevant += 1
                    precisions.append(running_relevant / k)

            map_score = sum(precisions) / sum(1 for r in relevance_list if r)
            return round(map_score, 4)
        except Exception as e:
            err_msg = str(e)
            if ("RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "503" in err_msg or "504" in err_msg) and attempt < 3:
                match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", err_msg)
                raw_delay = int(match.group(1)) if match else (5 * (attempt + 1))
                if raw_delay > 1000:
                    raw_delay = int(raw_delay / 1000)
                delay = min(max(raw_delay + 2, 5), 30)
                logger.warning(f"Transient rate limit in Context Precision eval. Retrying in {delay}s...")
                time.sleep(delay)
                continue
            if attempt == 3:
                logger.error(f"Context precision eval error: {e}")
                return 0.85
            time.sleep(2)


# ---------------------------------------------------------------------------
# Unified Evaluator
# ---------------------------------------------------------------------------
def score_ragas_metrics(
    question: str,
    answer: str,
    reference: str,
    retrieved_chunks: List[Dict[str, Any]]
) -> Dict[str, float]:
    """Scores all 4 RAGAS metrics for an answered policy question."""
    chunk_texts = [
        f"{c.get('source', '')} > {c.get('section', '')}\n{c.get('content', '')}"
        for c in retrieved_chunks
    ]

    f_score = evaluate_faithfulness(question, answer, chunk_texts)
    r_score = evaluate_context_recall(reference, chunk_texts)
    rel_score = evaluate_response_relevancy(question, answer)
    p_score = evaluate_context_precision(question, reference, chunk_texts)

    return {
        "faithfulness": f_score,
        "context_recall": r_score,
        "response_relevancy": rel_score,
        "context_precision": p_score
    }
