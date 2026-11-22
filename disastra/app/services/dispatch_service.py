from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from geoalchemy2.shape import to_shape
from shapely.geometry import Point

from app.models import Vehicle, Facility, SOSRequest, Dispatch, SeverityEnum
from app.services.routing_service import routing_service, haversine_distance
from app.services.facility_service import facility_service
from app.services.notify_service import notify_service

class DispatchService:
    async def create_dispatch(
        self,
        db: AsyncSession,
        sos_ids: List[UUID],
        vehicle_id: Optional[int] = None,
        facility_id: Optional[int] = None,
        batch: bool = False
    ) -> Dict[str, Any]:
        """
        Creates a dispatch for a single Red SOS or batched Yellow SOS (F8.2, F8.8, F8.9).
        - Auto-matches nearest suitable vehicle outside Red zone with enough capacity if vehicle_id not given.
        - Auto-selects nearest safe facility if facility_id not given.
        - Computes hazard-avoiding route.
        - Pre-alerts hospital (F6.6).
        - Dispatches notifications with URGENT marking for Red alerts (F8.3).
        """
        # Fetch SOS requests
        query = await db.execute(select(SOSRequest).where(SOSRequest.id.in_(sos_ids)))
        sos_list = query.scalars().all()
        if not sos_list:
            raise ValueError("No matching SOS requests found")

        is_red = any(s.severity == SeverityEnum.red for s in sos_list)
        total_people = sum(s.people_count for s in sos_list)
        
        # Pick primary location (centroid or first SOS)
        first_pt = to_shape(sos_list[0].location)
        pickup_lat, pickup_lon = first_pt.y, first_pt.x

        # 1. Resolve or Auto-match Facility
        facility = None
        if facility_id:
            f_res = await db.execute(select(Facility).where(Facility.id == facility_id))
            facility = f_res.scalar_one_or_none()
        
        if not facility:
            # Auto-match nearest safe facility
            nearest_facs = await facility_service.get_nearest_safe_facilities(
                db, lat=pickup_lat, lon=pickup_lon, limit=1, exclude_red_zone=True
            )
            if nearest_facs:
                f_res = await db.execute(select(Facility).where(Facility.id == nearest_facs[0]["id"]))
                facility = f_res.scalar_one_or_none()

        # 2. Resolve or Auto-match Vehicle
        vehicle = None
        if vehicle_id:
            v_res = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
            vehicle = v_res.scalar_one_or_none()

        if not vehicle:
            # Query available vehicles with capacity >= total_people
            v_query = await db.execute(
                select(Vehicle).where(
                    and_(
                        Vehicle.capacity >= total_people,
                        Vehicle.status.in_(["available", "busy"] if is_red else ["available"])
                    )
                )
            )
            candidates = v_query.scalars().all()
            if candidates:
                # Rank by distance to pickup location
                ranked_candidates = []
                for c in candidates:
                    v_pt = to_shape(c.last_location) if c.last_location else Point(pickup_lon, pickup_lat)
                    d = haversine_distance([pickup_lon, pickup_lat], [v_pt.x, v_pt.y])
                    ranked_candidates.append((d, c))
                ranked_candidates.sort(key=lambda x: x[0])
                vehicle = ranked_candidates[0][1]

        # 3. Compute Hazard-Aware Route
        destination_coords = [pickup_lon + 0.02, pickup_lat + 0.02] # default fallback
        if facility:
            f_pt = to_shape(facility.geometry)
            destination_coords = [f_pt.x, f_pt.y]

        route_info = await routing_service.compute_hazard_aware_route(
            db=db,
            origin=[pickup_lon, pickup_lat],
            destination=destination_coords,
            vehicle_type=vehicle.type if vehicle else "ambulance",
            avoid_hazards=True
        )

        # 4. Save Dispatch record
        dispatch = Dispatch(
            sos_ids=sos_ids,
            batch=batch or len(sos_ids) > 1,
            vehicle_id=vehicle.id if vehicle else None,
            facility_id=facility.id if facility else None,
            status="dispatched"
        )
        db.add(dispatch)

        # Update SOS status
        for s in sos_list:
            s.status = "in_progress"

        if vehicle:
            vehicle.status = "busy"

        await db.commit()
        await db.refresh(dispatch)

        # 5. Dispatch Notifications (F8.3, F6.6)
        alerts_dispatched = {}
        if vehicle:
            v_alert = await notify_service.send_transport_alert(
                vehicle_contact=vehicle.contact,
                provider_name=vehicle.provider,
                sos_level="red" if is_red else "yellow",
                pickup_lat=pickup_lat,
                pickup_lon=pickup_lon,
                destination_name=facility.name if facility else "Safe Zone Shelter",
                people_count=total_people,
                route_info=route_info
            )
            alerts_dispatched["transport"] = v_alert

        if facility:
            h_alert = await notify_service.pre_alert_hospital(
                hospital_contact=facility.contact or "hospital_ops@disastra.local",
                hospital_name=facility.name,
                sos_level="red" if is_red else "yellow",
                patient_count=total_people,
                eta_minutes=route_info["duration_min"]
            )
            alerts_dispatched["facility_pre_alert"] = h_alert

        return {
            "id": dispatch.id,
            "sos_ids": dispatch.sos_ids,
            "batch": dispatch.batch,
            "vehicle_id": dispatch.vehicle_id,
            "facility_id": dispatch.facility_id,
            "status": dispatch.status,
            "created_at": dispatch.created_at,
            "updated_at": dispatch.updated_at,
            "route_geometry": route_info["route_geometry"],
            "alerts_dispatched": alerts_dispatched
        }

dispatch_service = DispatchService()
