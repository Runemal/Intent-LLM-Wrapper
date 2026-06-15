from typing import Annotated

from fastapi import Depends, Request

from app.services.intent_service import IntentAnalysisService


def get_intent_service(request: Request) -> IntentAnalysisService:
    return request.app.state.container.intent_service


IntentServiceDep = Annotated[IntentAnalysisService, Depends(get_intent_service)]
