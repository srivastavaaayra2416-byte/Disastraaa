"""
Offline Geo script to generate and load flood masks, DEM, roads, and population (Section 8).
Hero event: Kerala Flood (or sample district) with Sentinel-1 SAR flood polygons,
WorldPop population overlay, and OpenStreetMap facilities/vehicles.
"""
import asyncio
from datetime import datetime, timezone
from shapely.geometry import Polygon, Point
from geoalchemy2.shape import from_shape

from app.core.database import AsyncSessionLocal
from app.models import ZoneCell, Facility, Vehicle, RoadReport

# Demo Region Coordinates: Kochi / Aluva flood zone (Kerala 2018 Hero Scenario)
# Center around ~10.1076° N, 76.3516° E

SAMPLE_ZONES = [
    {
        "zone_type": "red",
        "hazard_type": "flood",
        "confidence": 0.94,
        "population": 14200,
        "reason": "Water detected on Sentinel-1 SAR, elevation 2.5m, heavy river swelling",
        "coords": [
            [76.330, 10.090],
            [76.360, 10.090],
            [76.360, 10.120],
            [76.330, 10.120],
            [76.330, 10.090]
        ]
    },
    {
        "zone_type": "yellow",
        "hazard_type": "flood",
        "confidence": 0.82,
        "population": 28500,
        "reason": "1.5km buffer around inundated zone, forecast to rise within 24h",
        "coords": [
            [76.310, 10.070],
            [76.380, 10.070],
            [76.380, 10.140],
            [76.310, 10.140],
            [76.310, 10.070]
        ]
    },
    {
        "zone_type": "green",
        "hazard_type": "flood",
        "confidence": 0.98,
        "population": 65000,
        "reason": "High elevation ground (>25m), verified clear and passable",
        "coords": [
            [76.380, 10.140],
            [76.450, 10.140],
            [76.450, 10.200],
            [76.380, 10.200],
            [76.380, 10.140]
        ]
    }
]

SAMPLE_FACILITIES = [
    {
        "type": "hospital",
        "name": "General Hospital Ernakulam (Safe)",
        "lat": 10.160,
        "lon": 76.400,
        "capacity": 250,
        "beds_available": 45,
        "status": "open",
        "contact": "+91-484-2361234"
    },
    {
        "type": "hospital",
        "name": "Aluva Sub-District Hospital (Compromised - In Red Zone)",
        "lat": 10.105,
        "lon": 76.345,
        "capacity": 120,
        "beds_available": 0,
        "status": "waterlogged",
        "contact": "+91-484-2621111"
    },
    {
        "type": "shelter",
        "name": "Higher Secondary Relief Camp A",
        "lat": 10.170,
        "lon": 76.410,
        "capacity": 600,
        "beds_available": 240,
        "status": "open",
        "contact": "+91-9876543210"
    },
    {
        "type": "fire_station",
        "name": "North Paravur Rescue Base",
        "lat": 10.155,
        "lon": 76.395,
        "capacity": 50,
        "beds_available": 10,
        "status": "operational",
        "contact": "101"
    }
]

SAMPLE_VEHICLES = [
    {
        "type": "ambulance",
        "capacity": 2,
        "provider": "Kerala State Emergency 108",
        "contact": "+91-108-001",
        "status": "available",
        "lat": 10.165,
        "lon": 76.398
    },
    {
        "type": "boat",
        "capacity": 8,
        "provider": "NDRF Quick Response Team 4",
        "contact": "+91-9447012345",
        "status": "available",
        "lat": 10.135,
        "lon": 76.370
    },
    {
        "type": "bus",
        "capacity": 40,
        "provider": "KSRTC Disaster Evacuation Unit",
        "contact": "+91-9447099999",
        "status": "available",
        "lat": 10.180,
        "lon": 76.420
    }
]

SAMPLE_ROAD_REPORTS = [
    {
        "segment_id": "NH-544-Bridge-4",
        "status": "blocked",
        "reporter": "Field Scout Rajesh",
        "photo_url": "https://disastra.local/photos/flooded_bridge.jpg",
        "lat": 10.102,
        "lon": 76.348
    }
]

async def seed_data():
    print("Seeding Hero Scenario data into PostGIS...")
    async with AsyncSessionLocal() as db:
        # Seed Zones
        for z in SAMPLE_ZONES:
            poly = Polygon(z["coords"])
            cell = ZoneCell(
                geometry=from_shape(poly, srid=4326),
                zone_type=z["zone_type"],
                hazard_type=z["hazard_type"],
                confidence=z["confidence"],
                population=z["population"],
                reason=z["reason"],
                valid_from=datetime.now(timezone.utc),
                source="Sentinel-1 SAR / WorldPop 2018"
            )
            db.add(cell)

        # Seed Facilities
        for f in SAMPLE_FACILITIES:
            pt = Point(f["lon"], f["lat"])
            fac = Facility(
                type=f["type"],
                name=f["name"],
                geometry=from_shape(pt, srid=4326),
                capacity=f["capacity"],
                beds_available=f["beds_available"],
                status=f["status"],
                contact=f["contact"]
            )
            db.add(fac)

        # Seed Vehicles
        for v in SAMPLE_VEHICLES:
            pt = Point(v["lon"], v["lat"])
            veh = Vehicle(
                type=v["type"],
                capacity=v["capacity"],
                provider=v["provider"],
                contact=v["contact"],
                status=v["status"],
                last_location=from_shape(pt, srid=4326)
            )
            db.add(veh)

        # Seed Road Reports
        for r in SAMPLE_ROAD_REPORTS:
            pt = Point(r["lon"], r["lat"])
            rep = RoadReport(
                segment_id=r["segment_id"],
                status=r["status"],
                reporter=r["reporter"],
                photo_url=r["photo_url"],
                location=from_shape(pt, srid=4326),
                at=datetime.now(timezone.utc)
            )
            db.add(rep)

        await db.commit()
    print("Seed completed successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())
