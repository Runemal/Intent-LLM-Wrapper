from fastapi import APIRouter

from app.api.dependencies import IntentServiceDep
from app.schemas.intent import IntentAnalysisRequest, IntentAnalysisResponse

router = APIRouter(tags=["chat"])


@router.post("/message", response_model=IntentAnalysisResponse)
async def analyze_intent(
    payload: IntentAnalysisRequest,
    service: IntentServiceDep,
) -> IntentAnalysisResponse:
    return await service.analyze(payload)
