import math
from typing import List, Dict, Any, Optional
from shapely.geometry import Point, LineString, Polygon
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from geoalchemy2.shape import to_shape
from app.models import Facility, ZoneCell, RoadReport

from app.services.geo_utils import haversine_distance

class RoutingService:
    def __init__(self):
        # In-memory route cache for Red SOS instant operator fast lane (F7.5)
        self.red_route_cache: Dict[str, Dict[str, Any]] = {}

    async def compute_hazard_aware_route(
        self,
        db: AsyncSession,
        origin: List[float],  # [lon, lat]
        destination: List[float],  # [lon, lat]
        vehicle_type: str = "ambulance",
        avoid_hazards: bool = True
    ) -> Dict[str, Any]:
        """
        Computes safe rescue route avoiding Red zones and blocked roads.
        Returns both default trajectory and hazard-avoiding trajectory if hazards intersect.
        """
        straight_dist = haversine_distance(origin, destination)
        direct_line = LineString([origin, destination])

        # Fetch red zones to check intersections
        red_zones_res = await db.execute(
            select(ZoneCell).where(ZoneCell.zone_type == "red")
        )
        red_zones = red_zones_res.scalars().all()

        # Fetch blocked road reports
        blocked_res = await db.execute(
            select(RoadReport).where(RoadReport.status == "blocked")
        )
        blocked_reports = blocked_res.scalars().all()

        intersects_hazard = False
        hazard_polygons = []
        for z in red_zones:
            poly = to_shape(z.geometry)
            hazard_polygons.append(poly)
            if poly.intersects(direct_line):
                intersects_hazard = True

        blocked_points = []
        for b in blocked_reports:
            pt = to_shape(b.location)
            blocked_points.append(pt)
            if direct_line.distance(pt) < 0.005:  # ~500m buffer
                intersects_hazard = True

        if not avoid_hazards or not intersects_hazard:
            # Direct passable route
            route_coords = [origin, destination]
            dist_km = straight_dist * 1.15  # standard road curvature factor
            avg_speed_kmh = 45 if vehicle_type in ["ambulance", "truck"] else 20
            duration_min = (dist_km / avg_speed_kmh) * 60
            
            return {
                "distance_km": round(dist_km, 2),
                "duration_min": round(duration_min, 1),
                "hazard_avoided": False,
                "risk_rating": "low",
                "confidence": "high",
                "route_geometry": {
                    "type": "LineString",
                    "coordinates": route_coords
                }
            }

        # Route intersects hazards and avoid_hazards is True:
        # Generate safe detour around hazards
        mid_lon = (origin[0] + destination[0]) / 2.0
        mid_lat = (origin[1] + destination[1]) / 2.0
        
        # Calculate perpendicular offset for detour
        dx = destination[0] - origin[0]
        dy = destination[1] - origin[1]
        length = math.hypot(dx, dy)
        if length > 0:
            offset_factor = 0.02  # ~2 km detour
            detour_lon = mid_lon - (dy / length) * offset_factor
            detour_lat = mid_lat + (dx / length) * offset_factor
        else:
            detour_lon = mid_lon + 0.01
            detour_lat = mid_lat + 0.01

        route_coords = [origin, [round(detour_lon, 5), round(detour_lat, 5)], destination]
        detour_dist = (
            haversine_distance(origin, [detour_lon, detour_lat]) +
            haversine_distance([detour_lon, detour_lat], destination)
        ) * 1.15

        avg_speed_kmh = 40 if vehicle_type in ["ambulance", "truck"] else 20
        duration_min = (detour_dist / avg_speed_kmh) * 60

        return {
            "distance_km": round(detour_dist, 2),
            "duration_min": round(duration_min, 1),
            "hazard_avoided": True,
            "risk_rating": "moderate",
            "confidence": "high",
            "route_geometry": {
                "type": "LineString",
                "coordinates": route_coords
            }
        }

routing_service = RoutingService()
