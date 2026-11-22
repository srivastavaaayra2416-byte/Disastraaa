import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from geoalchemy2.shape import to_shape

from app.core.database import get_db
from app.core.redis import redis_manager
from app.core.config import settings
from app.models import SOSRequest, SeverityEnum, SOSStatusEnum
from app.schemas import (
    SOSCreate, SOSResponse, SOSSeverityUpdate, SMSPayload
)
from app.services.sos_service import sos_service
from app.services.sms_parser import parse_sms_payload

router = APIRouter(prefix="/sos", tags=["SOS"])

@router.post("", response_model=SOSResponse, status_code=201)
async def create_sos(
    sos_in: SOSCreate,
    x_user_role: Optional[str] = Header("victim", alias="X-User-Role"),
    db: AsyncSession = Depends(get_db)
):
    """
    Ingest an SOS from any channel (Internet, Mesh, Gateway).
    Includes rate limiting for Red (Section 13, F5.15) while never dropping genuine emergency.
    """
    if sos_in.severity == SeverityEnum.red:
        rate_key = f"rate_limit:red:{sos_in.device_id}"
        allowed = await redis_manager.check_rate_limit(
            rate_key,
            max_requests=settings.RED_RATE_LIMIT_PER_HOUR,
            window_sec=3600
        )
        if not allowed:
            # Guidelines rule: "excess Reds are flagged for review, not rejected. Never penalise."
            pass

    sos_record, _ = await sos_service.ingest_sos(db, sos_in)
    
    pt = to_shape(sos_record.location)
    return SOSResponse(
        id=sos_record.id,
        client_msg_id=sos_record.client_msg_id,
        device_id=sos_record.device_id,
        lat=pt.y,
        lon=pt.x,
        accuracy_m=sos_record.accuracy_m,
        severity=sos_record.severity,
        severity_changed_by=sos_record.severity_changed_by,
        severity_changed_at=sos_record.severity_changed_at,
        severity_reason=sos_record.severity_reason,
        need_type=sos_record.need_type,
        people_count=sos_record.people_count,
        battery_pct=sos_record.battery_pct,
        channel=sos_record.channel,
        status=sos_record.status,
        priority_score=sos_record.priority_score,
        zone_type=sos_record.zone_type,
        has_children=sos_record.has_children,
        has_elderly=sos_record.has_elderly,
        created_at=sos_record.created_at,
        received_at=sos_record.received_at,
        acknowledged_at=sos_record.acknowledged_at
    )

@router.post("/sms-webhook", response_model=SOSResponse, status_code=201)
async def sms_webhook(
    sms: SMSPayload,
    db: AsyncSession = Depends(get_db)
):
    """
    Ingest SMS payload e.g.: R*26.8467,80.9462*MED*3P*B12*22NOV1530
    Lenient parser, normalizes and routes to the exact same ingestion pipeline.
    """
    parsed = parse_sms_payload(sms.message)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_SMS_FORMAT", "message": "Failed to parse emergency coordinates or severity."}}
        )

    # Deterministic client_msg_id for deduplication
    client_msg_id = f"sms_{abs(hash(sms.message))}"
    sos_create = SOSCreate(
        client_msg_id=client_msg_id,
        device_id=sms.sender,
        lat=parsed["lat"],
        lon=parsed["lon"],
        severity=parsed["severity"],
        need_type=parsed["need_type"],
        people_count=parsed["people_count"],
        battery_pct=parsed["battery_pct"],
        channel="sms",
        created_at=parsed["created_at"]
    )

    sos_record, _ = await sos_service.ingest_sos(db, sos_create)
    pt = to_shape(sos_record.location)
    return SOSResponse(
        id=sos_record.id,
        client_msg_id=sos_record.client_msg_id,
        device_id=sos_record.device_id,
        lat=pt.y,
        lon=pt.x,
        accuracy_m=sos_record.accuracy_m,
        severity=sos_record.severity,
        severity_changed_by=sos_record.severity_changed_by,
        severity_changed_at=sos_record.severity_changed_at,
        severity_reason=sos_record.severity_reason,
        need_type=sos_record.need_type,
        people_count=sos_record.people_count,
        battery_pct=sos_record.battery_pct,
        channel=sos_record.channel,
        status=sos_record.status,
        priority_score=sos_record.priority_score,
        zone_type=sos_record.zone_type,
        has_children=sos_record.has_children,
        has_elderly=sos_record.has_elderly,
        created_at=sos_record.created_at,
        received_at=sos_record.received_at,
        acknowledged_at=sos_record.acknowledged_at
    )

@router.patch("/{sos_id}/severity", response_model=SOSResponse)
async def update_sos_severity(
    sos_id: uuid.UUID,
    update_data: SOSSeverityUpdate,
    x_user_role: Optional[str] = Header("victim", alias="X-User-Role"),
    db: AsyncSession = Depends(get_db)
):
    """
    F5.6 / Section 6.1: Upgrade or re-label level.
    - Victim can upgrade Yellow to Red anytime with no reason needed.
    - Downgrade/cancel requires explicit confirmation.
    - Control room re-label requires mandatory reason.
    - Recomputes priority score and emits dashboard re-sort event.
    """
    if x_user_role in ["control_room", "responder"]:
        update_data.actor = "control_room"

    try:
        updated = await sos_service.update_severity(db, sos_id, update_data)
        pt = to_shape(updated.location)
        return SOSResponse(
            id=updated.id,
            client_msg_id=updated.client_msg_id,
            device_id=updated.device_id,
            lat=pt.y,
            lon=pt.x,
            accuracy_m=updated.accuracy_m,
            severity=updated.severity,
            severity_changed_by=updated.severity_changed_by,
            severity_changed_at=updated.severity_changed_at,
            severity_reason=updated.severity_reason,
            need_type=updated.need_type,
            people_count=updated.people_count,
            battery_pct=updated.battery_pct,
            channel=updated.channel,
            status=updated.status,
            priority_score=updated.priority_score,
            zone_type=updated.zone_type,
            has_children=updated.has_children,
            has_elderly=updated.has_elderly,
            created_at=updated.created_at,
            received_at=updated.received_at,
            acknowledged_at=updated.acknowledged_at
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_SEVERITY_OPERATION", "message": str(e)}}
        )

@router.get("", response_model=List[SOSResponse])
async def get_sos_queue(
    severity: Optional[SeverityEnum] = None,
    need_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    cursor_id: Optional[uuid.UUID] = None,
    x_user_role: Optional[str] = Header("public", alias="X-User-Role"),
    db: AsyncSession = Depends(get_db)
):
    """
    Control Room & Dashboard SOS Queue:
    Strictly sorted by Severity first (all Red above Yellow), then priority_score DESC, received_at ASC.
    Location privacy: coordinates are fuzzed for public / unverified views (Section 13).
    """
    query = select(SOSRequest)
    filters = []

    if severity:
        filters.append(SOSRequest.severity == severity)
    if need_type:
        filters.append(SOSRequest.need_type == need_type)
    if cursor_id:
        # Simple cursor pagination support
        filters.append(SOSRequest.id != cursor_id)

    if filters:
        query = query.where(and_(*filters))

    # ORDER BY severity (red first), priority_score DESC, received_at ASC
    query = query.order_by(
        SOSRequest.severity.asc(),  # 'red' before 'yellow' alphabetically
        SOSRequest.priority_score.desc(),
        SOSRequest.received_at.asc()
    ).limit(limit)

    res = await db.execute(query)
    results = res.scalars().all()

    # Apply location privacy fuzzing if user is not authorized responder/control room (F4.7)
    is_authorized = x_user_role in ["control_room", "responder", "volunteer"]

    output = []
    for r in results:
        pt = to_shape(r.location)
        lat = pt.y if is_authorized else round(pt.y, 2)
        lon = pt.x if is_authorized else round(pt.x, 2)
        output.append(
            SOSResponse(
                id=r.id,
                client_msg_id=r.client_msg_id,
                device_id=r.device_id if is_authorized else "***masked***",
                lat=lat,
                lon=lon,
                accuracy_m=r.accuracy_m,
                severity=r.severity,
                severity_changed_by=r.severity_changed_by,
                severity_changed_at=r.severity_changed_at,
                severity_reason=r.severity_reason,
                need_type=r.need_type,
                people_count=r.people_count,
                battery_pct=r.battery_pct,
                channel=r.channel,
                status=r.status,
                priority_score=r.priority_score,
                zone_type=r.zone_type,
                has_children=r.has_children,
                has_elderly=r.has_elderly,
                created_at=r.created_at,
                received_at=r.received_at,
                acknowledged_at=r.acknowledged_at
            )
        )

    return output
