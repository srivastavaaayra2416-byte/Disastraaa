import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from geoalchemy2.shape import to_shape

from app.core.database import get_db
from app.models import ZoneCell
from app.schemas import ZoneCellResponse, PopulationSummaryResponse

router = APIRouter(tags=["Zones & Population"])

@router.get("/zones")
async def get_zones(
    bbox: Optional[str] = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    hazard: Optional[str] = Query("flood"),
    format: str = Query("geojson", pattern="^(geojson|list)$"),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns zone polygons with data freshness and explainability reason.
    Returns standard GeoJSON FeatureCollection or vector tile friendly format.
    """
    query = select(ZoneCell)
    if hazard:
        query = query.where(ZoneCell.hazard_type == hazard)

    res = await db.execute(query)
    cells = res.scalars().all()

    features = []
    for c in cells:
        geom = to_shape(c.geometry)
        geom_dict = {
            "type": "Polygon",
            "coordinates": [list(geom.exterior.coords)]
        }
        feature = {
            "type": "Feature",
            "id": c.id,
            "geometry": geom_dict,
            "properties": {
                "id": c.id,
                "zone_type": c.zone_type,
                "hazard_type": c.hazard_type,
                "confidence": c.confidence,
                "population": c.population,
                "reason": c.reason,
                "valid_from": c.valid_from.isoformat(),
                "source": c.source
            }
        }
        features.append(feature)

    if format == "geojson":
        return {
            "type": "FeatureCollection",
            "features": features,
            "source_freshness": datetime.now(timezone.utc).isoformat()
        }

    return [f["properties"] for f in features]

@router.get("/population", response_model=PopulationSummaryResponse)
async def get_population(
    zone: Optional[str] = Query(None),
    hazard: str = Query("flood"),
    db: AsyncSession = Depends(get_db)
):
    """
    Impact panel data: population counts for Red, Yellow, Green zones and vulnerable groups.
    """
    query = select(ZoneCell).where(ZoneCell.hazard_type == hazard)
    res = await db.execute(query)
    cells = res.scalars().all()

    red_pop = sum(c.population for c in cells if c.zone_type == "red")
    yellow_pop = sum(c.population for c in cells if c.zone_type == "yellow")
    green_pop = sum(c.population for c in cells if c.zone_type == "green")
    total_pop = red_pop + yellow_pop + green_pop

    # Estimated vulnerable demographics (approx 15% children, 12% elderly)
    vulnerable_groups = {
        "children": int(total_pop * 0.15),
        "elderly": int(total_pop * 0.12),
        "estimated_boats_needed": max(1, red_pop // 50),
        "food_packets_needed": red_pop * 3
    }

    return PopulationSummaryResponse(
        hazard_type=hazard,
        red_population=red_pop,
        yellow_population=yellow_pop,
        green_population=green_pop,
        total_population=total_pop,
        vulnerable_groups=vulnerable_groups,
        timestamp=datetime.now(timezone.utc)
    )
