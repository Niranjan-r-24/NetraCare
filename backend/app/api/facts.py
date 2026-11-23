from typing import Optional
from fastapi import APIRouter, Query
from app.schemas import FactOfTheDayOut
from app.services.llm import LLMService

router = APIRouter(prefix="/fact-of-the-day", tags=["Fact of the Day"])

@router.get("", response_model=FactOfTheDayOut)
def get_fact_of_the_day(previous: Optional[str] = Query(None, description="Previous fact to avoid repeating")):
    """
    Returns an educational, friendly eye health fact for patients.
    Supports a refresh action passing previous fact.
    """
    result = LLMService.get_fact_of_the_day(previous_fact=previous)
    return FactOfTheDayOut(
        fact=result["fact"],
        caveat=result["caveat"]
    )
