from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from geoalchemy2.shape import to_shape
from shapely.geometry import Point

from app.core.database import get_db
from app.models import Vehicle, Dispatch
from app.schemas import DispatchCreate, DispatchResponse
from app.services.dispatch_service import dispatch_service

router = APIRouter(prefix="/dispatch", tags=["Dispatch & Transport"])

@router.post("", response_model=DispatchResponse, status_code=201)
async def create_dispatch(
    dispatch_in: DispatchCreate,
    x_user_role: Optional[str] = Header("control_room", alias="X-User-Role"),
    db: AsyncSession = Depends(get_db)
):
    """
    POST /dispatch creates dispatch and alerts providers (F8.2, F8.3, F8.8, F8.9).
    Accepts single Red SOS (fast lane) or Yellow batch.
    Pre-alerts destination hospital and issues SMS/Push alerts to transport operators.
    """
    try:
        result = await dispatch_service.create_dispatch(
            db=db,
            sos_ids=dispatch_in.sos_ids,
            vehicle_id=dispatch_in.vehicle_id,
            facility_id=dispatch_in.facility_id,
            batch=dispatch_in.batch
        )
        return DispatchResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "DISPATCH_FAILED", "message": str(e)}}
        )

@router.get("/vehicles")
async def list_vehicles(
    db: AsyncSession = Depends(get_db)
):
    """Returns transport providers and current operational status (F8.1, F8.5)."""
    res = await db.execute(select(Vehicle))
    vehicles = res.scalars().all()
    output = []
    for v in vehicles:
        loc = to_shape(v.last_location) if v.last_location else None
        output.append({
            "id": v.id,
            "type": v.type,
            "capacity": v.capacity,
            "provider": v.provider,
            "contact": v.contact,
            "status": v.status,
            "lat": loc.y if loc else None,
            "lon": loc.x if loc else None
        })
    return output
