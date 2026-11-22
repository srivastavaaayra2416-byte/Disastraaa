import asyncio
import logging
from datetime import datetime, timezone
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from geoalchemy2.shape import to_shape

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import (
    SOSRequest, SOSEventLog, ZoneCell, SeverityEnum, SOSStatusEnum
)
from app.services.scoring import compute_priority_score
from app.services.notify_service import notify_service
from app.core.redis import redis_manager

logger = logging.getLogger(__name__)

class EscalationWorker:
    """
    Background escalation worker according to Section 7 (F5.7):
    Watches open SOS and applies:
    - Red unacknowledged for > 2 min: Re-broadcast on all channels, alert next responder tier, log escalated.
    - Yellow unacknowledged for > 30 min: Raise to Red review.
    - Yellow location turns a Red zone: Raise to Red review.
    - Yellow battery under 10%: Raise to Red review.
    - 3+ Yellow in the same grid cell: Raise to Red review.
    Every step is idempotent so restarts do not double-escalate.
    """

    async def run_escalation_cycle(self, db: AsyncSession):
        now_utc = datetime.now(timezone.utc)
        
        # 1. Fetch unacknowledged / open SOS requests
        open_statuses = [SOSStatusEnum.received, SOSStatusEnum.pending, SOSStatusEnum.relayed]
        query = await db.execute(
            select(SOSRequest).where(SOSRequest.status.in_(open_statuses))
        )
        open_sos = query.scalars().all()
        if not open_sos:
            return

        # Preload Red Zones
        red_zones_res = await db.execute(select(ZoneCell).where(ZoneCell.zone_type == "red"))
        red_zones = [to_shape(z.geometry) for z in red_zones_res.scalars().all()]

        # Yellow clusters map by grid coordinate (~1km cell approx 0.01 deg)
        yellow_cell_counts = {}
        for item in open_sos:
            if item.severity == SeverityEnum.yellow:
                pt = to_shape(item.location)
                cell_key = (round(pt.x, 2), round(pt.y, 2))
                yellow_cell_counts[cell_key] = yellow_cell_counts.get(cell_key, 0) + 1

        for sos in open_sos:
            # Check existing event logs to ensure idempotency for specific triggers
            events_query = await db.execute(
                select(SOSEventLog).where(
                    and_(SOSEventLog.sos_id == sos.id, SOSEventLog.event == "escalated")
                )
            )
            existing_escalations = events_query.scalars().all()
            escalated_reasons = [e.detail.get("rule") for e in existing_escalations if e.detail]

            pt = to_shape(sos.location)
            created_at = sos.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            elapsed_seconds = (now_utc - created_at).total_seconds()

            # Rule 1: Red unacknowledged for > 2 min (configurable)
            if sos.severity == SeverityEnum.red and sos.status != SOSStatusEnum.acknowledged:
                if elapsed_seconds >= settings.RED_ESCALATION_TIMEOUT_SEC:
                    rule_key = "red_unacknowledged_timeout"
                    if rule_key not in escalated_reasons:
                        logger.warning(f"[ESCALATION] Red SOS {sos.id} unacknowledged for {elapsed_seconds}s! Re-broadcasting.")
                        log = SOSEventLog(
                            sos_id=sos.id,
                            event="escalated",
                            actor="system",
                            detail={
                                "rule": rule_key,
                                "elapsed_sec": elapsed_seconds,
                                "action": "Re-broadcast on all channels & alert next responder tier"
                            }
                        )
                        db.add(log)
                        await notify_service.notify_volunteers_nearby(
                            sos_id=sos.id,
                            severity="red",
                            lat=pt.y,
                            lon=pt.x
                        )
                        await redis_manager.publish("dashboard:escalations", {
                            "sos_id": str(sos.id),
                            "action": "red_re_broadcast",
                            "rule": rule_key
                        })

            # Yellow Escalation Rules
            if sos.severity == SeverityEnum.yellow:
                should_raise = False
                trigger_reason = None
                rule_name = None

                # Rule 2: Yellow unacknowledged for > 30 min (configurable)
                if elapsed_seconds >= settings.YELLOW_ESCALATION_TIMEOUT_SEC:
                    rule_name = "yellow_timeout"
                    if rule_name not in escalated_reasons:
                        should_raise = True
                        trigger_reason = f"Unacknowledged for {int(elapsed_seconds//60)} min"

                # Rule 3: Yellow location turns a Red zone
                if not should_raise and any(poly.contains(pt) for poly in red_zones):
                    rule_name = "yellow_in_red_zone"
                    if rule_name not in escalated_reasons:
                        should_raise = True
                        trigger_reason = "Location turned into active Red hazard zone"

                # Rule 4: Yellow battery under 10%
                if not should_raise and sos.battery_pct is not None and sos.battery_pct < 10:
                    rule_name = "yellow_critical_battery"
                    if rule_name not in escalated_reasons:
                        should_raise = True
                        trigger_reason = f"Critical low battery: {sos.battery_pct}%"

                # Rule 5: 3+ Yellow in the same grid cell
                cell_key = (round(pt.x, 2), round(pt.y, 2))
                if not should_raise and yellow_cell_counts.get(cell_key, 0) >= 3:
                    rule_name = "yellow_cluster_density"
                    if rule_name not in escalated_reasons:
                        should_raise = True
                        trigger_reason = f"Dense cluster of {yellow_cell_counts[cell_key]} requests in same cell"

                if should_raise and rule_name:
                    logger.info(f"[ESCALATION] Raising Yellow SOS {sos.id} to Red Review. Reason: {trigger_reason}")
                    # Update severity & score
                    sos.severity_changed_by = "system"
                    sos.severity_changed_at = now_utc
                    sos.severity_reason = f"Auto-escalated for Red Review: {trigger_reason}"
                    
                    # Log escalation
                    log = SOSEventLog(
                        sos_id=sos.id,
                        event="escalated",
                        actor="system",
                        detail={"rule": rule_name, "reason": trigger_reason}
                    )
                    db.add(log)
                    
                    # Notify dashboard operator for urgent review
                    await redis_manager.publish("dashboard:escalations", {
                        "sos_id": str(sos.id),
                        "rule": rule_name,
                        "reason": trigger_reason,
                        "action": "urgent_review_required"
                    })

        await db.commit()

async def start_worker():
    """Periodic worker sweep as a safety net (Section 7)."""
    worker = EscalationWorker()
    logger.info("Starting Escalation Worker background loop...")
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await worker.run_escalation_cycle(session)
        except Exception as e:
            logger.error(f"Error in escalation worker cycle: {e}")
        await asyncio.sleep(settings.ESCALATION_SWEEP_INTERVAL_SEC)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_worker())
