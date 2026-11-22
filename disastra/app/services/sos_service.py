import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update
from geoalchemy2.shape import to_shape, from_shape
from shapely.geometry import Point

from app.models import (
    SOSRequest, SOSEventLog, ZoneCell, SeverityEnum, SOSStatusEnum
)
from app.schemas import SOSCreate, SOSSeverityUpdate
from app.services.scoring import compute_priority_score
from app.services.notify_service import notify_service
from app.core.redis import redis_manager
from app.core.config import settings

class SOSService:
    async def get_zone_at_point(self, db: AsyncSession, point: Point) -> str:
        """Determines whether point lies in a Red, Yellow, or Green zone."""
        res = await db.execute(select(ZoneCell))
        cells = res.scalars().all()
        for cell in cells:
            poly = to_shape(cell.geometry)
            if poly.contains(point):
                return cell.zone_type.lower()
        return "green"

    async def ingest_sos(
        self,
        db: AsyncSession,
        sos_in: SOSCreate
    ) -> Tuple[SOSRequest, bool]:
        """
        Ingestion pipeline according to Section 5.3:
        1. Validate & normalize input.
        2. Idempotency: Unique on (device_id, client_msg_id).
        3. Deduplication rule (F5.12): at most 1 active Red and 1 active Yellow per device.
           A new Red from a device with active Yellow upgrades that record instead of creating duplicate.
        4. Lookup zone type using ST_Contains.
        5. Compute priority_score (severity-first).
        6. Log created (and relayed / received) in sos_event_log.
        7. Publish to dashboard channel, and for Red, trigger volunteer push within 5km.
        """
        # 1. Check idempotency (same client_msg_id and device_id)
        existing_msg_query = await db.execute(
            select(SOSRequest).where(
                and_(
                    SOSRequest.device_id == sos_in.device_id,
                    SOSRequest.client_msg_id == sos_in.client_msg_id
                )
            )
        )
        existing_msg = existing_msg_query.scalar_one_or_none()
        if existing_msg:
            return existing_msg, False

        loc_point = Point(sos_in.lon, sos_in.lat)
        zone_type = await self.get_zone_at_point(db, loc_point)
        now_utc = datetime.now(timezone.utc)
        created_time = sos_in.created_at or now_utc

        # 2. Check deduplication / upgrade rule (F5.12):
        active_statuses = [SOSStatusEnum.pending, SOSStatusEnum.relayed, SOSStatusEnum.received, SOSStatusEnum.acknowledged, SOSStatusEnum.in_progress]
        
        # Check active requests for this device
        active_query = await db.execute(
            select(SOSRequest).where(
                and_(
                    SOSRequest.device_id == sos_in.device_id,
                    SOSRequest.status.in_(active_statuses)
                )
            )
        )
        active_requests = active_query.scalars().all()

        active_yellow = next((r for r in active_requests if r.severity == SeverityEnum.yellow), None)
        active_red = next((r for r in active_requests if r.severity == SeverityEnum.red), None)

        # If incoming is RED and there is an active YELLOW -> Upgrade that record!
        if sos_in.severity == SeverityEnum.red and active_yellow:
            active_yellow.severity = SeverityEnum.red
            active_yellow.severity_changed_by = "victim"
            active_yellow.severity_changed_at = now_utc
            active_yellow.severity_reason = "Upgraded via incoming Red SOS"
            active_yellow.need_type = sos_in.need_type or active_yellow.need_type
            active_yellow.people_count = sos_in.people_count
            active_yellow.battery_pct = sos_in.battery_pct if sos_in.battery_pct is not None else active_yellow.battery_pct
            active_yellow.zone_type = zone_type
            active_yellow.priority_score = compute_priority_score(
                severity="red",
                need_type=active_yellow.need_type,
                has_children=active_yellow.has_children or sos_in.has_children,
                has_elderly=active_yellow.has_elderly or sos_in.has_elderly,
                zone_type=zone_type,
                battery_pct=active_yellow.battery_pct,
                created_at=active_yellow.created_at
            )

            # Log upgrade event
            event = SOSEventLog(
                sos_id=active_yellow.id,
                event="upgraded",
                actor="victim",
                detail={"reason": "Incoming Red SOS upgraded active Yellow SOS", "channel": sos_in.channel}
            )
            db.add(event)
            await db.commit()
            await db.refresh(active_yellow)

            # Pub/sub notification to dashboard
            await self._publish_sos_event(active_yellow, "upgraded")
            # Red volunteer alert within 5 km
            await notify_service.notify_volunteers_nearby(
                sos_id=active_yellow.id,
                severity="red",
                lat=sos_in.lat,
                lon=sos_in.lon
            )
            return active_yellow, False

        # If duplicate incoming with same active severity already exists, update details but don't duplicate
        if sos_in.severity == SeverityEnum.red and active_red:
            active_red.client_msg_id = sos_in.client_msg_id
            active_red.battery_pct = sos_in.battery_pct if sos_in.battery_pct is not None else active_red.battery_pct
            await db.commit()
            await db.refresh(active_red)
            return active_red, False

        if sos_in.severity == SeverityEnum.yellow and active_yellow:
            active_yellow.client_msg_id = sos_in.client_msg_id
            active_yellow.battery_pct = sos_in.battery_pct if sos_in.battery_pct is not None else active_yellow.battery_pct
            await db.commit()
            await db.refresh(active_yellow)
            return active_yellow, False

        # 3. Create fresh SOS Record
        priority = compute_priority_score(
            severity=sos_in.severity.value,
            need_type=sos_in.need_type,
            has_children=sos_in.has_children,
            has_elderly=sos_in.has_elderly,
            zone_type=zone_type,
            battery_pct=sos_in.battery_pct,
            created_at=created_time
        )

        sos_record = SOSRequest(
            id=uuid.uuid4(),
            client_msg_id=sos_in.client_msg_id,
            device_id=sos_in.device_id,
            location=from_shape(loc_point, srid=4326),
            accuracy_m=sos_in.accuracy_m,
            severity=sos_in.severity,
            need_type=sos_in.need_type,
            people_count=sos_in.people_count,
            battery_pct=sos_in.battery_pct,
            channel=sos_in.channel,
            status=SOSStatusEnum.received,
            priority_score=priority,
            zone_type=zone_type,
            has_children=sos_in.has_children,
            has_elderly=sos_in.has_elderly,
            created_at=created_time,
            received_at=now_utc
        )
        db.add(sos_record)

        # Event log
        log_created = SOSEventLog(
            sos_id=sos_record.id,
            event="received",
            actor=sos_in.channel or "victim",
            detail={"zone": zone_type, "channel": sos_in.channel, "priority_score": priority}
        )
        db.add(log_created)

        await db.commit()
        await db.refresh(sos_record)

        # Publish to dashboard
        await self._publish_sos_event(sos_record, "received")

        # Volunteer alert if Red
        if sos_record.severity == SeverityEnum.red:
            await notify_service.notify_volunteers_nearby(
                sos_id=sos_record.id,
                severity="red",
                lat=sos_in.lat,
                lon=sos_in.lon
            )

        return sos_record, True

    async def update_severity(
        self,
        db: AsyncSession,
        sos_id: uuid.UUID,
        update_data: SOSSeverityUpdate
    ) -> SOSRequest:
        """
        PATCH /sos/{id}/severity logic according to Section 6.1 (F5.6):
        - Victim upgrade Yellow to Red: allowed any time, one call, no reason needed.
        - Victim downgrade or cancel: requires an explicit confirm flag.
        - Control-room re-label: reason is mandatory, rejected without it.
        - Writes severity_changed_by/at/reason and sos_event_log row.
        - Recomputes score and pushes re-sorted queue to dashboard.
        """
        sos_query = await db.execute(select(SOSRequest).where(SOSRequest.id == sos_id))
        sos = sos_query.scalar_one_or_none()
        if not sos:
            raise ValueError("SOS record not found")

        old_severity = sos.severity
        new_severity = update_data.severity

        # Validation rules:
        if update_data.actor == "control_room":
            if not update_data.reason or not update_data.reason.strip():
                raise ValueError("Control room re-label requires a mandatory reason.")
        elif update_data.actor == "victim":
            # Downgrade check
            if old_severity == SeverityEnum.red and new_severity == SeverityEnum.yellow:
                if not update_data.confirm:
                    raise ValueError("Victim downgrade from Red to Yellow requires explicit confirmation flag.")

        now_utc = datetime.now(timezone.utc)
        sos.severity = new_severity
        sos.severity_changed_by = update_data.actor
        sos.severity_changed_at = now_utc
        sos.severity_reason = update_data.reason

        # Recompute priority score
        sos.priority_score = compute_priority_score(
            severity=new_severity.value,
            need_type=sos.need_type,
            has_children=sos.has_children,
            has_elderly=sos.has_elderly,
            zone_type=sos.zone_type,
            battery_pct=sos.battery_pct,
            created_at=sos.created_at
        )

        event_name = "upgraded" if new_severity == SeverityEnum.red else "relabelled"
        log = SOSEventLog(
            sos_id=sos.id,
            event=event_name,
            actor=update_data.actor,
            detail={
                "from": old_severity.value,
                "to": new_severity.value,
                "reason": update_data.reason
            }
        )
        db.add(log)

        await db.commit()
        await db.refresh(sos)

        # Notify dashboard of resort
        await self._publish_sos_event(sos, event_name)

        if new_severity == SeverityEnum.red:
            pt = to_shape(sos.location)
            await notify_service.notify_volunteers_nearby(
                sos_id=sos.id,
                severity="red",
                lat=pt.y,
                lon=pt.x
            )

        return sos

    async def _publish_sos_event(self, sos: SOSRequest, event_type: str):
        pt = to_shape(sos.location)
        payload = {
            "event": event_type,
            "sos_id": str(sos.id),
            "severity": sos.severity.value,
            "status": sos.status.value,
            "priority_score": sos.priority_score,
            "lat": pt.y,
            "lon": pt.x,
            "need_type": sos.need_type,
            "people_count": sos.people_count,
            "zone_type": sos.zone_type,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await redis_manager.publish("dashboard:sos_updates", payload)

sos_service = SOSService()
