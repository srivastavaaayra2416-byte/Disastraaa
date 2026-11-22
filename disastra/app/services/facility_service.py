from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from app.models import Facility, ZoneCell
from app.services.routing_service import haversine_distance

class FacilityService:
    async def get_nearest_safe_facilities(
        self,
        db: AsyncSession,
        lat: float,
        lon: float,
        facility_type: Optional[str] = None,
        limit: int = 3,
        exclude_red_zone: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Returns nearest safe facilities by route time / distance (F6.2).
        Excludes facilities located inside a Red zone (F6.4) and flags them.
        """
        user_pt = Point(lon, lat)
        
        # Load all Red zones for filtering
        red_zones_res = await db.execute(
            select(ZoneCell).where(ZoneCell.zone_type == "red")
        )
        red_polygons = [to_shape(z.geometry) for z in red_zones_res.scalars().all()]

        # Query facilities
        query = select(Facility)
        if facility_type:
            query = query.where(Facility.type == facility_type)
            
        result = await db.execute(query)
        facilities = result.scalars().all()

        scored_facilities = []
        for fac in facilities:
            pt = to_shape(fac.geometry)
            fac_lon, fac_lat = pt.x, pt.y
            
            # Check if facility is inside any Red zone
            in_red = any(poly.contains(pt) for poly in red_polygons)
            
            dist_km = haversine_distance([lon, lat], [fac_lon, fac_lat])
            # Estimate ETA: 40 km/h average rescue speed
            eta_min = (dist_km / 40.0) * 60.0

            fac_dict = {
                "id": fac.id,
                "type": fac.type,
                "name": fac.name,
                "lat": fac_lat,
                "lon": fac_lon,
                "capacity": fac.capacity,
                "beds_available": fac.beds_available,
                "status": fac.status,
                "contact": fac.contact,
                "distance_km": round(dist_km, 2),
                "eta_minutes": round(eta_min, 1),
                "in_red_zone": in_red
            }

            if exclude_red_zone and in_red:
                continue

            scored_facilities.append(fac_dict)

        # Sort by distance / route time
        scored_facilities.sort(key=lambda x: x["distance_km"])
        return scored_facilities[:limit]

facility_service = FacilityService()
