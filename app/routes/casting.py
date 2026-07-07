from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_llm_service
from app.schemas import CastingDraftRequest, CastingDraftResponse
from app.utils.llm_service import LLMService


router = APIRouter(prefix="/v1/casting", tags=["casting"])
logger = logging.getLogger(__name__)


@router.post("/draft", response_model=CastingDraftResponse)
async def generate_casting_draft(
    request: CastingDraftRequest,
    llm_service: LLMService = Depends(get_llm_service),
) -> CastingDraftResponse:
    """Return a structured casting draft without going through the general chat agent."""
    if not request.rough_idea.strip() and not request.context.strip():
        raise HTTPException(status_code=400, detail="rough_idea or context is required")

    try:
        return await llm_service.generate_casting_draft(
            rough_idea=request.rough_idea,
            context=request.context,
        )
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        logger.exception("Casting draft generation failed")
        raise HTTPException(status_code=503, detail="Casting AI service unavailable") from error
