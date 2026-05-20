from fastapi import APIRouter, HTTPException
from schemas.request import AdvisoryRequestSchema
from schemas.response import AdvisoryResponseSchema
from services import generate_full_advisory
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/v1/api/advisory/external/generate", response_model=AdvisoryResponseSchema)
async def generate_advisory_endpoint(request: AdvisoryRequestSchema):
    try:
        # Pass the validated request to your business logic layer
        response_data = generate_full_advisory(request)
        return response_data
    except Exception as e:
        logger.error(f"Error generating advisory: {str(e)}", exc_info=True)
        return AdvisoryResponseSchema(
            success=False,
            message=str(e),
            yield_data=None,
            activitiesToDo=[]
        )