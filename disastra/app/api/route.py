from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas import RouteRequest, RouteResponse
from app.services.routing_service import routing_service

router = APIRouter(prefix="/route", tags=["Routing"])

@router.post("", response_model=RouteResponse)
async def compute_route(
    request: RouteRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Computes rescue and evacuation routes avoiding hazard polygons and road blocks (F7.2, F7.5).
    Can compare default route vs hazard-avoiding route.
    """
    try:
        route_result = await routing_service.compute_hazard_aware_route(
            db=db,
            origin=request.origin,
            destination=request.destination,
            vehicle_type=request.vehicle_type,
            avoid_hazards=request.avoid_hazards
        )
        return RouteResponse(**route_result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "ROUTING_ERROR", "message": str(e)}}
        )
