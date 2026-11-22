from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas import FacilityResponse
from app.services.facility_service import facility_service

router = APIRouter(prefix="/facilities", tags=["Facilities"])

@router.get("/nearest", response_model=List[FacilityResponse])
async def get_nearest_facilities(
    lat: float = Query(..., description="Latitude of user or cluster"),
    lon: float = Query(..., description="Longitude of user or cluster"),
    type: Optional[str] = Query(None, description="hospital | shelter | fire_station"),
    limit: int = Query(3, ge=1, le=10),
    exclude_red: bool = Query(True, description="Automatically exclude facilities inside Red zones"),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns nearest facilities by route time and distance (F6.2).
    Automatically flags and excludes facilities located within active Red flood zones (F6.4).
    """
    facilities = await facility_service.get_nearest_safe_facilities(
        db=db,
        lat=lat,
        lon=lon,
        facility_type=type,
        limit=limit,
        exclude_red_zone=exclude_red
    )
    return [FacilityResponse(**f) for f in facilities]
