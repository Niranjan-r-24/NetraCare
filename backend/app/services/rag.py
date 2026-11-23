import os
import re
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from pydantic import BaseModel, Field
from rank_bm25 import BM25Okapi
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import settings
from app.services.llm import LLMService, LLMServiceException
from app.services.telemetry import track

logger = logging.getLogger("netracare.rag")

# Required fixed literal strings per Handout R4, R5
I_DONT_KNOW_RESPONSE = "I don't know. Our clinic documents don't cover that. Please ask Staff at the front desk."
RAG_FAILURE_RESPONSE = "Sorry, I can't answer just now. Please try again, or ask Staff at the front desk."

class RAGAnswerOutput(BaseModel):
    answer: str = Field(description="Direct, concise answer in at most 120 words.")
    source_ids: List[str] = Field(default_factory=list, description="IDs of chunks directly used to answer.")
    answered: bool = Field(description="True if chunks contain sufficient facts to answer, False otherwise.")

class ChunkItem:
    def __init__(self, chunk_id: str, source: str, section: str, content: str):
        self.chunk_id = chunk_id
        self.source = source
        self.section = section
        self.content = content

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source": self.source,
            "section": self.section,
            "content": self.content
        }

def clean_slug(text: str) -> str:
    cleaned = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[-\s]+', '_', cleaned)

def tokenize_bm25(text: str) -> List[str]:
    """Lowercase text and strip punctuation so 'Menon?' matches 'Menon'."""
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    return [w for w in cleaned.split() if w]

class RAGService:
    _chunks: Optional[List[ChunkItem]] = None
    _bm25: Optional[BM25Okapi] = None
    _bm25_corpus: Optional[List[List[str]]] = None
    _vectorstore: Optional[Chroma] = None

    @classmethod
    def get_embedding_function(cls) -> Optional[GoogleGenerativeAIEmbeddings]:
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
        return GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=api_key
        )

    @classmethod
    def load_and_chunk_documents(cls) -> List[ChunkItem]:
        """
        Load the 3 Markdown documents from docs/iteration-3/data/documents/.
        Split by '## ' headings first so each chunk belongs to one section.
        Split a section again only if it exceeds 1000 characters (chunk_size=1000, chunk_overlap=100).
        """
        docs_dir = settings.resolved_iter3_data_dir / "documents"
        target_files = ["clinic_policy_faq.md", "doctors.md", "procedures.md"]

        chunks: List[ChunkItem] = []
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            separators=["\n\n", "\n", " ", ""]
        )

        for filename in target_files:
            file_path = docs_dir / filename
            if not file_path.exists():
                logger.warning(f"Knowledge base document not found: {file_path}")
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Split by markdown ## headings
            raw_sections = re.split(r'\n(?=##\s+)', content)
            for sec_text in raw_sections:
                sec_text = sec_text.strip()
                if not sec_text:
                    continue

                # Check if it has a ## heading
                if sec_text.startswith("##"):
                    lines = sec_text.split("\n", 1)
                    heading = lines[0].replace("##", "").strip()
                    body = lines[1].strip() if len(lines) > 1 else ""
                else:
                    # Preamble before the first ## heading (e.g. # Title and intro)
                    lines = sec_text.split("\n", 1)
                    heading = lines[0].replace("#", "").strip()
                    body = lines[1].strip() if len(lines) > 1 else ""

                full_sec_text = f"## {heading}\n{body}".strip()
                base_id = f"{filename.replace('.md', '')}_{clean_slug(heading)}"

                if len(full_sec_text) > 1000:
                    sub_chunks = text_splitter.split_text(full_sec_text)
                    for idx, sub_text in enumerate(sub_chunks):
                        content_with_heading = sub_text if sub_text.startswith("##") else f"## {heading}\n{sub_text}".strip()
                        chunks.append(ChunkItem(
                            chunk_id=f"{base_id}_{idx}",
                            source=filename,
                            section=heading,
                            content=content_with_heading
                        ))
                else:
                    chunks.append(ChunkItem(
                        chunk_id=f"{base_id}_0",
                        source=filename,
                        section=heading,
                        content=full_sec_text
                    ))

        logger.info(f"Loaded and chunked knowledge base: {len(chunks)} chunks.")
        return chunks

    @classmethod
    def get_chunks(cls) -> List[ChunkItem]:
        if cls._chunks is None:
            cls._chunks = cls.load_and_chunk_documents()
        return cls._chunks

    @classmethod
    def get_bm25_retriever(cls) -> Tuple[BM25Okapi, List[ChunkItem]]:
        if cls._bm25 is None:
            chunks = cls.get_chunks()
            corpus = [tokenize_bm25(c.content) for c in chunks]
            cls._bm25 = BM25Okapi(corpus)
            cls._bm25_corpus = corpus
        return cls._bm25, cls.get_chunks()

    @classmethod
    def get_vectorstore(cls) -> Optional[Chroma]:
        if cls._vectorstore is not None:
            return cls._vectorstore

        persist_dir = str(settings.resolved_chroma_dir)
        emb_fn = cls.get_embedding_function()
        if not emb_fn:
            logger.warning("No embedding function available (missing GEMINI_API_KEY).")
            return None

        if Path(persist_dir).exists() and any(Path(persist_dir).iterdir()):
            cls._vectorstore = Chroma(
                collection_name="netracare_kb",
                embedding_function=emb_fn,
                persist_directory=persist_dir
            )
            return cls._vectorstore
        return None

    @classmethod
    def build_index(cls) -> int:
        """
        Build and persist Chroma vector store from the knowledge base chunks.
        Called by build_index.py CLI.
        """
        chunks = cls.load_and_chunk_documents()
        cls._chunks = chunks

        emb_fn = cls.get_embedding_function()
        if not emb_fn:
            raise ValueError("Cannot build index: GEMINI_API_KEY is not configured.")

        persist_dir = str(settings.resolved_chroma_dir)
        os.makedirs(persist_dir, exist_ok=True)

        texts = [c.content for c in chunks]
        metadatas = [
            {"chunk_id": c.chunk_id, "source": c.source, "section": c.section}
            for c in chunks
        ]
        ids = [c.chunk_id for c in chunks]

        # Initialize and populate Chroma
        cls._vectorstore = Chroma(
            collection_name="netracare_kb",
            embedding_function=emb_fn,
            persist_directory=persist_dir
        )
        cls._vectorstore.reset_collection()
        cls._vectorstore.add_texts(texts=texts, metadatas=metadatas, ids=ids)

        # Also initialize in-memory BM25
        corpus = [tokenize_bm25(c.content) for c in chunks]
        cls._bm25 = BM25Okapi(corpus)
        cls._bm25_corpus = corpus

        logger.info(f"Persisted {len(chunks)} chunks into Chroma at {persist_dir}.")
        return len(chunks)

    # =========================================================================
    # Hybrid Retrieval (Equal-Weight BM25 + Vector)
    # =========================================================================
    @classmethod
    def hybrid_search(cls, query: str, top_k: int = 4) -> Dict[str, Any]:
        """
        Combine BM25 keyword search and Chroma vector search with equal weighting (0.5 / 0.5).
        Scores are normalized using min-max normalization before combining.
        Returns top chunks for keyword_only, vector_only, and hybrid.
        """
        chunks = cls.get_chunks()
        chunk_map = {c.chunk_id: c for c in chunks}
        bm25, _ = cls.get_bm25_retriever()

        # 1. BM25 scoring
        q_tokens = tokenize_bm25(query)
        bm25_raw_scores = bm25.get_scores(q_tokens) if q_tokens else [0.0] * len(chunks)
        
        # Build BM25 ranking
        bm25_results = []
        for c, s in zip(chunks, bm25_raw_scores):
            bm25_results.append((c.chunk_id, float(s)))
        bm25_results.sort(key=lambda x: x[1], reverse=True)

        # Min-max normalization for BM25 scores
        max_bm25 = max(bm25_raw_scores) if len(bm25_raw_scores) > 0 else 0.0
        min_bm25 = min(bm25_raw_scores) if len(bm25_raw_scores) > 0 else 0.0
        range_bm25 = (max_bm25 - min_bm25) if (max_bm25 - min_bm25) > 1e-9 else 1.0

        bm25_norm: Dict[str, float] = {}
        for c, s in zip(chunks, bm25_raw_scores):
            if max_bm25 > 0:
                bm25_norm[c.chunk_id] = (s - min_bm25) / range_bm25
            else:
                bm25_norm[c.chunk_id] = 0.0

        # 2. Vector scoring
        vstore = cls.get_vectorstore()
        vec_norm: Dict[str, float] = {}
        vec_raw: Dict[str, float] = {}
        vec_results = []

        if vstore:
            try:
                # search all or top 20
                docs_scores = vstore.similarity_search_with_relevance_scores(query, k=len(chunks))
                raw_vec_scores = [score for _, score in docs_scores]
                max_vec = max(raw_vec_scores) if raw_vec_scores else 0.0
                min_vec = min(raw_vec_scores) if raw_vec_scores else 0.0
                range_vec = (max_vec - min_vec) if (max_vec - min_vec) > 1e-9 else 1.0

                for doc, score in docs_scores:
                    cid = doc.metadata.get("chunk_id")
                    if cid:
                        vec_raw[cid] = float(score)
                        vec_norm[cid] = (score - min_vec) / range_vec if range_vec > 0 else 1.0
                        vec_results.append((cid, float(score)))
            except Exception as e:
                logger.error(f"Vector search failed: {e}")

        # 3. Equal-Weight Hybrid Combination
        hybrid_scores: Dict[str, float] = {}
        all_cids = set(c.chunk_id for c in chunks)
        for cid in all_cids:
            s_bm25 = bm25_norm.get(cid, 0.0)
            s_vec = vec_norm.get(cid, 0.0)
            # Mathematically justified equal-weight combination of normalized scores
            hybrid_scores[cid] = 0.5 * s_bm25 + 0.5 * s_vec

        hybrid_ranked = sorted(hybrid_scores.items(), key=lambda x: x[1], reverse=True)

        def format_results(ranked_list: List[Tuple[str, float]], limit: int = 4) -> List[Dict[str, Any]]:
            res = []
            for cid, score in ranked_list[:limit]:
                c = chunk_map.get(cid)
                if c:
                    res.append({
                        "source": c.source,
                        "section": c.section,
                        "chunk_id": c.chunk_id,
                        "content": c.content,
                        "score": round(score, 4)
                    })
            return res

        return {
            "keyword_only": format_results(bm25_results, top_k),
            "vector_only": format_results(vec_results, top_k),
            "hybrid": format_results(hybrid_ranked, top_k)
        }

    # =========================================================================
    # Question Rewriter Chain
    # =========================================================================
    @classmethod
    def rewrite_question(cls, current_message: str, history: List[Dict[str, str]]) -> str:
        """
        Rewrite patient's follow-up message into a complete standalone search question.
        Returns the original query if history is empty or question is already complete.
        """
        clean_msg = current_message.strip()
        if not history:
            return clean_msg

        # Filter last 6 messages
        recent_history = history[-6:]
        history_str = "\n".join([f"{m.get('role', 'user').title()}: {m.get('content', '')}" for m in recent_history])

        prompt_text = (
            "You are a helpful question rewriter for NetraCare Eye Clinic assistant.\n"
            "Given the recent conversation history and the patient's latest message, rewrite the latest message "
            "into a clear, standalone search query that includes all necessary context (such as doctor names, procedures, or topics mentioned earlier).\n\n"
            "STRICT RULES:\n"
            "1. Resolve pronouns (it, they, that, this, the surgery, the drops, etc.) into the exact medical topic or entity from history.\n"
            "2. If the patient's message is already a complete, standalone question, output it unchanged.\n"
            "3. Do NOT answer the question. Output ONLY the rewritten standalone question.\n\n"
            f"CONVERSATION HISTORY:\n{history_str}\n\n"
            f"LATEST PATIENT MESSAGE: \"{clean_msg}\"\n\n"
            "STANDALONE SEARCH QUERY:"
        )

        rewritten = clean_msg
        for attempt in range(4):
            try:
                model = LLMService.get_model(temperature=0.0, timeout=20)
                prompt = ChatPromptTemplate.from_template("{instruction}")
                chain = prompt | model | StrOutputParser()
                res = chain.invoke({"instruction": prompt_text}).strip()
                if res.startswith('"') and res.endswith('"'):
                    res = res[1:-1].strip()
                rewritten = res or clean_msg
                break
            except Exception as e:
                err_msg = str(e)
                if ("RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg) and attempt < 3:
                    match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", err_msg)
                    raw_delay = int(match.group(1)) if match else 12
                    if raw_delay > 1000:
                        raw_delay = int(raw_delay / 1000)
                    delay = min(max(raw_delay + 2, 5), 25)
                    time.sleep(delay)
                    continue
                logger.warning(f"Question rewrite failed: {e}. Using raw message.")
                return clean_msg
        return rewritten

    # =========================================================================
    # Grounded Answer Generation & Citation Validation (R5 & R6)
    # =========================================================================
    @classmethod
    @track(name="generate_grounded_answer", tags=["rag"])
    def generate_grounded_answer(cls, question: str, retrieved_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate answer strictly from retrieved chunks with Pydantic output.
        Validates citations in Python: returns I_DONT_KNOW_RESPONSE if evidence insufficient or citations invalid.
        """
        if not retrieved_chunks:
            return {
                "answer": I_DONT_KNOW_RESPONSE,
                "sources": [],
                "is_error": False
            }

        chunks_context = "\n\n".join([
            f"[Chunk ID: {c['chunk_id']}]\nFile: {c['source']}\nSection: {c['section']}\nContent:\n{c['content']}"
            for c in retrieved_chunks
        ])

        parser = PydanticOutputParser(pydantic_object=RAGAnswerOutput)

        system_prompt = (
            "You are the patient assistant for NetraCare Eye Speciality Clinic.\n"
            "Answer the patient's question strictly and only using the retrieved clinic document chunks provided below.\n\n"
            "CRITICAL SAFETY & ANSWERING RULES:\n"
            "1. GROUNDING: Answer ONLY from facts stated in the retrieved chunks. If the chunks do not answer the question, set answered=false and source_ids=[].\n"
            "2. NO DIAGNOSIS: Never say what condition the patient might have (e.g. do not diagnose cataract, glaucoma, retinal detachment, dry eye, etc.).\n"
            "3. NO TREATMENT RECOMMENDATIONS: Never suggest or recommend any treatments, surgeries, remedies, medicines, or specific eye drops.\n"
            "4. SPECIALITY ROUTING: When a patient describes symptoms or an eye problem, suggest which clinic speciality to book and list ALL matching doctors who cover that speciality from doctors.md (e.g., 'A Glaucoma specialist can assess this. At NetraCare that is Dr. Meera Iyer. The doctor will assess you at your visit.').\n"
            "   - Children under 16 must be routed to Paediatric with Dr. Vikram Menon.\n"
            "   - Patients who are unsure or have general issues (routine eye test, new glasses, mild watering/itching, reading headaches) should be routed to General with Dr. Anand Rao, Dr. Kiran Shah, and Dr. Vikram Menon.\n"
            "   - If a problem is not about the eyes (e.g., rash on arm, earache), state politely that NetraCare only cares for eye problems.\n"
            "5. DIRECT BOOKING: The assistant cannot check slot availability or book appointments. ONLY if the patient explicitly asks to book or check free slots, explain that you cannot check slots or book and direct the patient to the Book page. Do NOT include booking disclaimers if the patient did not ask to book.\n"
            "6. INDICATIVE COSTS: When answering questions about procedure costs, state the price range from the retrieved document (e.g. ₹35,000 to ₹90,000 per eye) and note that all procedure costs are indicative only and confirmed by Staff at the clinic. Do NOT discuss costs on non-cost questions.\n"
            "7. RELEVANCE & CONCISENESS: Answer ONLY what the patient specifically asked about. Do not volunteer unsolicited advice, unrelated disclaimers, or extraneous procedure facts.\n"
            "8. LENGTH: The answer must be at most 120 words.\n"
            "9. SOURCE IDS: In source_ids, return ONLY the exact chunk IDs (e.g., 'procedures_cataract_surgery_0') from the chunks that directly support your answer.\n\n"
            "{format_instructions}\n"
        )

        user_prompt = (
            "RETRIEVED CLINIC DOCUMENT CHUNKS:\n"
            f"{chunks_context}\n\n"
            "PATIENT QUESTION: \"{question}\""
        )

        parsed = None
        for attempt in range(4):
            try:
                model = LLMService.get_model(temperature=0.0, timeout=30)
                prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt),
                    ("user", user_prompt)
                ]).partial(format_instructions=parser.get_format_instructions())

                chain = prompt | model | parser
                parsed = chain.invoke({"question": question})
                break
            except Exception as e:
                err_msg = str(e)
                is_transient = any(code in err_msg for code in ["RESOURCE_EXHAUSTED", "429", "503", "504", "UNAVAILABLE", "DEADLINE"])
                if is_transient and attempt < 3:
                    match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", err_msg)
                    raw_delay = int(match.group(1)) if match else (3 * (attempt + 1))
                    if raw_delay > 1000:
                        raw_delay = int(raw_delay / 1000)
                    delay = min(max(raw_delay + 1, 3), 25)
                    logger.warning(f"Transient failure in grounded answer ({err_msg[:60]}...). Retrying in {delay}s (attempt {attempt + 1}/3)...")
                    time.sleep(delay)
                    continue
                logger.error(f"Grounded answer generation failed: {e}")
                return {
                    "answer": RAG_FAILURE_RESPONSE,
                    "sources": [],
                    "is_error": True
                }

        if parsed is None:
            return {
                "answer": RAG_FAILURE_RESPONSE,
                "sources": [],
                "is_error": True
            }

        # Code-side citation validation
        retrieved_chunk_ids = {c["chunk_id"] for c in retrieved_chunks}
        valid_source_ids = [sid for sid in parsed.source_ids if sid in retrieved_chunk_ids]

        # If answered=False or source_ids empty or hallucinated non-retrieved IDs
        if not parsed.answered or len(valid_source_ids) == 0 or len(valid_source_ids) != len(parsed.source_ids):
            return {
                "answer": I_DONT_KNOW_RESPONSE,
                "sources": [],
                "is_error": False
            }

        # Map valid source IDs to unique citation strings "file › section"
        chunk_lookup = {c["chunk_id"]: c for c in retrieved_chunks}
        sources_list: List[str] = []
        seen_src = set()
        for sid in valid_source_ids:
            chk = chunk_lookup.get(sid)
            if chk:
                citation = f"{chk['source']} › {chk['section']}"
                if citation not in seen_src:
                    seen_src.add(citation)
                    sources_list.append(citation)

        return {
            "answer": parsed.answer.strip(),
            "sources": sources_list,
            "is_error": False
        }
