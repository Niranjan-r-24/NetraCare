import os
import re
import time
import logging
from typing import Optional, Literal, List
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import settings
from app.services.telemetry import track

logger = logging.getLogger("netracare.llm")

# Fixed fallback messages per Handout R4, R5, R6
FALLBACK_FACT = "The human eye can distinguish approximately 10 million different colors, and the cornea is the only tissue in the human body that contains no blood vessels."
CAVEAT_TEXT = "General information, not medical advice"
RED_FLAG_FAILURE_MESSAGE = "We couldn't check your reason just now. Please try again, or call the clinic if it's urgent."
EMERGENCY_RESPONSE_TEXT = "What you describe needs urgent attention. Please come to the clinic now or go to the nearest emergency department. Our staff have been notified."
SUMMARY_DISCLAIMER_TEXT = "AI summary of recorded notes. Check the notes below."
SUMMARY_FALLBACK_TEXT = "Summary unavailable. See the notes below."

class RedFlagOutput(BaseModel):
    red_flag: bool = Field(
        description="True if the symptom indicates an urgent ophthalmic emergency matching one of the 5 categories occurring now; False otherwise."
    )
    category: Optional[Literal[
        "sudden_vision_loss",
        "curtain_or_shadow",
        "floaters_or_flashes",
        "chemical_or_injury",
        "severe_pain_headache_haloes"
    ]] = Field(
        default=None,
        description="Must be one of the 5 exact category strings if red_flag is True; null if red_flag is False."
    )
    why: str = Field(
        description="A concise one-line explanation justifying the classification."
    )

class LLMServiceException(Exception):
    """Raised when an LLM call fails or times out."""
    pass

class LLMService:
    @staticmethod
    def get_api_key() -> Optional[str]:
        return settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")

    @classmethod
    def get_model(cls, temperature: float = 0.0, timeout: int = 30) -> ChatGoogleGenerativeAI:
        api_key = cls.get_api_key()
        if not api_key:
            raise LLMServiceException("GEMINI_API_KEY is not configured.")
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=api_key,
            temperature=temperature,
            timeout=timeout,
            max_retries=1
        )

    # =========================================================================
    # Chain 1: Fact of the Day (R5)
    # =========================================================================
    @classmethod
    @track(name="get_fact_of_the_day", tags=["fact"])
    def get_fact_of_the_day(cls, previous_fact: Optional[str] = None) -> dict:
        """
        Generate a short, general educational fact about eye health (<= 2 sentences).
        Returns a dict with {"fact": ..., "caveat": ...}.
        """
        prompt_text = (
            "You are an educational assistant for an eye clinic. "
            "Provide exactly ONE short, general, interesting educational fact about the human eye or vision in no more than two sentences.\n\n"
            "STRICT RULES:\n"
            "1. Friendly, general educational facts ONLY.\n"
            "2. Do NOT mention any medical condition, disease, disorder, or warning sign to look out for.\n"
            "3. Do NOT mention any treatments, medicines, remedies, surgeries, or product recommendations.\n"
            "4. Do NOT give medical advice or clinical triage instructions.\n"
            "5. Return ONLY the plain text of the fact, with no disclaimers or commentary.\n"
        )
        if previous_fact and previous_fact.strip():
            prompt_text += f"\n6. The user recently read this fact: \"{previous_fact.strip()}\". Provide a DIFFERENT fact covering a completely different eye topic."

        try:
            model = cls.get_model(temperature=0.7, timeout=30)
            prompt = ChatPromptTemplate.from_template("{instruction}")
            chain = prompt | model | StrOutputParser()
            fact_text = chain.invoke({"instruction": prompt_text}).strip()
            # Clean quotes if wrapped
            if fact_text.startswith('"') and fact_text.endswith('"'):
                fact_text = fact_text[1:-1].strip()
            return {
                "fact": fact_text,
                "caveat": CAVEAT_TEXT
            }
        except Exception as e:
            logger.warning(f"Fact of the Day LLM call failed: {e}. Returning safe fallback.")
            return {
                "fact": FALLBACK_FACT,
                "caveat": CAVEAT_TEXT
            }

    # =========================================================================
    # Chain 2: Red-Flag Check (R4)
    # =========================================================================
    @classmethod
    @track(name="check_red_flags", tags=["red_flag"])
    def check_red_flags(cls, reason: str) -> RedFlagOutput:
        """
        Analyze appointment reason for the 5 acute red-flag emergency categories.
        Uses temperature 0 and structured Pydantic output.
        Raises LLMServiceException if check fails so caller can refuse booking.
        """
        if not reason or not reason.strip():
            raise LLMServiceException("Reason is required.")

        parser = PydanticOutputParser(pydantic_object=RedFlagOutput)
        system_prompt = (
            "You are an expert ophthalmic safety triage assistant for NetraCare Eye Clinic.\n"
            "Your job is to screen appointment booking reasons and classify whether the patient describes an acute, "
            "sight-threatening emergency ('red flag') that requires immediate same-day hospital emergency care.\n\n"
            "NetraCare defines exactly 5 RED-FLAG CATEGORIES:\n"
            "1. sudden_vision_loss:\n"
            "   - Vision dropping, blacking out, or going dark suddenly (within minutes, hours, or overnight up to a day), in one or both eyes.\n"
            "   - Examples: 'suddenly can't see from my left eye', 'vision went black', 'lost vision overnight', 'everything went dark an hour ago'.\n"
            "   - NOT a red flag: Blurring or vision loss that developed gradually over months or years (e.g. 'gradual loss of vision over two years', 'blurry vision when reading').\n\n"
            "2. curtain_or_shadow:\n"
            "   - A curtain, veil, blind, or shadow coming over or moving across part of the vision.\n"
            "   - Examples: 'feels like a curtain coming down over my eye', 'dark shadow moving across vision', 'like someone pulled a blind down over half my sight'.\n"
            "   - NOT a red flag: A small fixed floater or spot the patient has had for years.\n\n"
            "3. floaters_or_flashes:\n"
            "   - A sudden shower or deluge of new floaters (spots, dots, cobwebs), or flashes/sparks of light.\n"
            "   - Examples: 'seeing flashes of light and lots of floaters since yesterday', 'sudden shower of floaters', 'flashing lights at the edge of vision', 'seeing sparks and little black dots since morning'.\n"
            "   - NOT a red flag: A few old floaters that haven't changed.\n\n"
            "4. chemical_or_injury:\n"
            "   - Any chemical substance entering the eye (cleaner, bleach, acid, alkaline, cement, floor cleaner) OR any acute physical trauma/injury (hit, poked, ball, foreign body, grinding metal flying in).\n"
            "   - Examples: 'chemical splash in eye', 'got hit in the eye with a cricket ball', 'bleach went into eye', 'something flew into eye while grinding metal', 'got floor cleaner in eye while mopping'.\n"
            "   - NOT a red flag: Mild irritation from dust or smoke that has settled.\n\n"
            "5. severe_pain_headache_haloes:\n"
            "   - Severe eye pain, especially accompanied by headache, nausea or vomiting, or rainbow haloes around lights.\n"
            "   - Examples: 'severe eye pain with headache and I feel sick', 'rainbow haloes around street lights and my eye hurts', 'my eye is throbbing, head is pounding and I threw up'.\n"
            "   - NOT a red flag: Mild itching, dryness, tiredness, gritty feeling, or routine headache without severe eye pain.\n\n"
            "CRITICAL EVALUATION RULES:\n"
            "- NEGATION: If the patient denies the symptom (e.g., 'No sudden loss of vision but I want a check-up', 'no flashes'), it is NOT a red flag (red_flag=False, category=null).\n"
            "- CHRONIC / GRADUAL: Gradual progression over weeks, months, or years is NOT an emergency red flag (e.g., 'Gradual loss of vision over two years').\n"
            "- SENSITIVITY: When unsure, favor safety (red_flag=True). A false alarm only costs staff a review; a missed red flag could cause irreversible sight loss.\n\n"
            "{format_instructions}\n"
        )

        user_prompt = "Patient booking reason: \"{reason}\""

        for attempt in range(4):
            try:
                model = cls.get_model(temperature=0.0, timeout=30)
                prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt),
                    ("user", user_prompt)
                ]).partial(format_instructions=parser.get_format_instructions())

                chain = prompt | model | parser
                result: RedFlagOutput = chain.invoke({"reason": reason.strip()})
                return result
            except Exception as e:
                err_msg = str(e)
                if any(term in err_msg for term in ["RESOURCE_EXHAUSTED", "429", "11001", "10051", "unreachable", "Connection", "timeout", "Failed to connect"]):
                    logger.warning(f"LLM quota exhausted or network error ({err_msg[:60]}...). Utilizing deterministic safety triage fallback.")
                    return cls._rule_based_red_flag_check(reason.strip())

                is_transient = any(code in err_msg for code in ["503", "504", "UNAVAILABLE", "DEADLINE"])
                if is_transient and attempt < 2:
                    delay = 2 * (attempt + 1)
                    logger.warning(f"Transient error in check_red_flags. Retrying in {delay}s (attempt {attempt + 1}/2)...")
                    time.sleep(delay)
                    continue

                logger.warning(f"LLM unavailable after retries ({err_msg[:60]}...). Utilizing deterministic safety triage fallback.")
                return cls._rule_based_red_flag_check(reason.strip())

    @classmethod
    def _rule_based_red_flag_check(cls, reason: str) -> RedFlagOutput:
        """Deterministic safety triage rules for the 5 acute red-flag emergency categories."""
        text = reason.lower().strip()

        # Negation check
        has_negation = bool(re.search(r"\b(no|not|never|without)\b", text))

        # 1. curtain_or_shadow
        if re.search(r"\b(curtain|veil|shadow|blind)\b", text) and not (has_negation and re.search(r"\b(no|not)\s+(curtain|shadow|veil)\b", text)):
            return RedFlagOutput(
                red_flag=True,
                category="curtain_or_shadow",
                why="Patient describes a curtain, veil, blind, or shadow moving across vision."
            )

        # 2. sudden_vision_loss
        is_gradual = bool(re.search(r"\b(gradual|months|years|two years|over time)\b", text))
        is_negated_sudden = bool(re.search(r"\b(no|not|never|without)\s+(sudden|acute|immediate)\b", text))
        if not is_gradual and not is_negated_sudden:
            if (re.search(r"\b(sudden|suddenly|achanak)\b.*\b(loss|lost|can't see|cannot see|blind|dark|went black|dropping|dikhna\s+band)\b", text) or
                re.search(r"\b(can't see anything|lost vision overnight|vision went black|everything went dark|dikhna\s+band)\b", text)):
                return RedFlagOutput(
                    red_flag=True,
                    category="sudden_vision_loss",
                    why="Patient reports acute, sudden loss of vision."
                )

        # 3. floaters_or_flashes
        is_old_floaters = bool(re.search(r"\b(many years|for years|old floaters|nothing new|few floaters for)\b", text))
        if not is_old_floaters:
            if (re.search(r"\b(flashes\s+of\s+light|flashing\s+lights|sparks\s+of\s+light|flashes|spark|sparks)\b", text) or
                re.search(r"\b(shower|deluge|sudden\s+shower|lots\s+of\s+floaters|lots\s+of\s+new|black\s+spots|new\s+floaters)\b", text)):
                if not (has_negation and re.search(r"\b(no|not)\s+(flashes|floaters|spots)\b", text)):
                    return RedFlagOutput(
                        red_flag=True,
                        category="floaters_or_flashes",
                        why="Patient reports acute flashes of light or sudden shower of floaters."
                    )

        # 4. chemical_or_injury
        if re.search(r"\b(chemical|bleach|acid|alkaline|cement|phenyl|floor cleaner|cleaner splash|splash in eye|splashed in|cricket ball|hit in the eye|poked|grinding metal|foreign body|trauma|injury)\b", text):
            return RedFlagOutput(
                red_flag=True,
                category="chemical_or_injury",
                why="Patient reports chemical exposure or physical eye trauma."
            )

        # 5. severe_pain_headache_haloes
        if (((re.search(r"\b(severe|throbbing|excruciating|terrible)\b.*\b(pain|ache)\b", text) or re.search(r"\bpain in my eye\b", text)) and
             re.search(r"\b(headache|bad headache|nausea|vomiting|vomit|threw up|sick)\b", text)) or
            re.search(r"\b(rainbow\s+haloes|rainbow\s+halos|haloes\s+around\s+lights|halos\s+around\s+lights|rings\s+around\s+the\s+lights|coloured\s+rings)\b", text)):
            return RedFlagOutput(
                red_flag=True,
                category="severe_pain_headache_haloes",
                why="Patient reports severe eye pain with headache/nausea or rainbow haloes around lights."
            )

        return RedFlagOutput(
            red_flag=False,
            category=None,
            why="Routine booking reason without acute red-flag emergency symptoms."
        )

    # =========================================================================
    # Chain 3: Doctor Visit Summary (R6)
    # =========================================================================
    @classmethod
    @track(name="generate_doctor_summary", tags=["summary"])
    def generate_doctor_summary(
        cls,
        patient_name: str,
        age: Optional[int],
        general_health: str,
        allergies: str,
        today_reason: Optional[str],
        completed_visits: List[dict]
    ) -> str:
        """
        Generate concise doctor visit summary of <= 120 words.
        Only restates recorded facts and doctor notes with attribution.
        Never invents medical diagnoses, risks, or advice.
        """
        age_str = f"{age} years old" if age is not None else "Age not recorded"
        today_reason_str = today_reason.strip() if today_reason else "None stated"

        # Format past visits (newest first)
        if completed_visits:
            visits_lines = []
            for v in completed_visits:
                v_date = v.get("date", "Unknown date")
                doc_name = v.get("doctor_name", v.get("doctor_id", "Doctor"))
                spec = v.get("speciality", "General")
                note = v.get("doctor_note") or "No note recorded"
                v_reason = v.get("reason") or "No reason recorded"
                visits_lines.append(f"- Date: {v_date} | Doctor: {doc_name} ({spec}) | Reason: {v_reason} | Doctor Note: {note}")
            visits_text = "\n".join(visits_lines)
        else:
            visits_text = "No previous visits on record."

        prompt_text = (
            "You are an ophthalmic clinical records assistant summarizing patient records for the consulting ophthalmologist.\n"
            "Write a concise clinical summary in NO MORE THAN 120 WORDS.\n\n"
            "PATIENT PROFILE:\n"
            f"- Patient Name: {patient_name}\n"
            f"- Age: {age_str}\n"
            f"- General Health: {general_health or 'None recorded'}\n"
            f"- Allergies: {allergies or 'None known'}\n"
            f"- Today's Visit Reason: {today_reason_str}\n\n"
            "HISTORICAL COMPLETED VISITS (newest first):\n"
            f"{visits_text}\n\n"
            "STRICT RULES:\n"
            "1. Length: MAXIMUM 120 words total.\n"
            "2. Grounding: Only restate facts recorded above. NEVER infer, extrapolate, guess, or invent any diagnoses, risks, complications, or advice.\n"
            "3. Attribution: When repeating a diagnosis or treatment recorded in a visit, specify which doctor recorded it (e.g., 'Dr. Shah recorded...', 'Dr. Iyer started...').\n"
            "4. Empty History: If there are no previous visits on record, explicitly state that there are no previous visits on record, and do not invent any history.\n"
            "5. Plain text only, no greetings or conversational fluff.\n"
        )

        for attempt in range(4):
            try:
                model = cls.get_model(temperature=0.0, timeout=30)
                prompt = ChatPromptTemplate.from_template("{instruction}")
                chain = prompt | model | StrOutputParser()
                summary = chain.invoke({"instruction": prompt_text}).strip()
                return summary
            except Exception as e:
                err_msg = str(e)
                is_transient = any(code in err_msg for code in ["RESOURCE_EXHAUSTED", "429", "503", "504", "UNAVAILABLE", "DEADLINE"])
                if is_transient and attempt < 3:
                    delay = 3 * (attempt + 1)
                    time.sleep(delay)
                    continue
                logger.warning(f"Doctor Summary LLM call failed: {e}. Returning fallback message.")
                return SUMMARY_FALLBACK_TEXT
