from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from geoalchemy2.shape import to_shape, from_shape
from shapely.geometry import Point

from app.core.database import get_db
from app.models import RoadReport
from app.schemas import RoadReportCreate, RoadReportResponse

router = APIRouter(prefix="/road-report", tags=["Road Reports"])

@router.post("", response_model=RoadReportResponse, status_code=201)
async def submit_road_report(
    report_in: RoadReportCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Crowd-sourced blocked or clear road reporting by volunteers and citizens (F7.6).
    Updates routing hazard model dynamically.
    """
    pt = Point(report_in.lon, report_in.lat)
    report = RoadReport(
        segment_id=report_in.segment_id,
        status=report_in.status.lower(),
        reporter=report_in.reporter,
        photo_url=report_in.photo_url,
        location=from_shape(pt, srid=4326),
        at=datetime.now(timezone.utc)
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return RoadReportResponse(
        id=report.id,
        segment_id=report.segment_id,
        status=report.status,
        reporter=report.reporter,
        photo_url=report.photo_url,
        lat=report_in.lat,
        lon=report_in.lon,
        at=report.at
    )

@router.get("", response_model=List[RoadReportResponse])
async def list_road_reports(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Lists crowd-sourced road condition reports."""
    query = select(RoadReport)
    if status:
        query = query.where(RoadReport.status == status.lower())
    
    res = await db.execute(query.order_by(RoadReport.at.desc()))
    items = res.scalars().all()
    
    output = []
    for r in items:
        pt = to_shape(r.location)
        output.append(
            RoadReportResponse(
                id=r.id,
                segment_id=r.segment_id,
                status=r.status,
                reporter=r.reporter,
                photo_url=r.photo_url,
                lat=pt.y,
                lon=pt.x,
                at=r.at
            )
        )
    return output
