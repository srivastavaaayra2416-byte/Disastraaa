from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from app.models import SeverityEnum, SOSStatusEnum

# Base GeoJSON representations
class PointGeometry(BaseModel):
    type: str = "Point"
    coordinates: List[float] # [lon, lat]

class PolygonGeometry(BaseModel):
    type: str = "Polygon"
    coordinates: List[List[List[float]]]

class LineStringGeometry(BaseModel):
    type: str = "LineString"
    coordinates: List[List[float]]

# SOS Schemas
class SOSCreate(BaseModel):
    client_msg_id: str
    device_id: str
    lat: float
    lon: float
    accuracy_m: Optional[float] = None
    severity: SeverityEnum # 'red' | 'yellow'
    need_type: Optional[str] = "OTHER" # MED, TRAP, FOOD, EVAC, OTHER
    people_count: int = 1
    battery_pct: Optional[int] = None
    channel: str = "internet" # internet | sms | mesh | gateway
    has_children: bool = False
    has_elderly: bool = False
    created_at: Optional[datetime] = None

class SOSSeverityUpdate(BaseModel):
    severity: SeverityEnum # 'red' | 'yellow'
    actor: str = "victim" # victim | control_room
    reason: Optional[str] = None
    confirm: bool = False # required for downgrade / cancel

class SOSResponse(BaseModel):
    id: UUID
    client_msg_id: str
    device_id: str
    lat: float
    lon: float
    accuracy_m: Optional[float] = None
    severity: SeverityEnum
    severity_changed_by: Optional[str] = None
    severity_changed_at: Optional[datetime] = None
    severity_reason: Optional[str] = None
    need_type: Optional[str] = None
    people_count: int
    battery_pct: Optional[int] = None
    channel: Optional[str] = None
    status: SOSStatusEnum
    priority_score: int
    zone_type: Optional[str] = None
    has_children: bool = False
    has_elderly: bool = False
    created_at: datetime
    received_at: datetime
    acknowledged_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# SMS Gateway Webhook
class SMSPayload(BaseModel):
    sender: str
    message: str # Format: R*26.8467,80.9462*MED*3P*B12*22NOV1530

# Zone Schemas
class ZoneCellResponse(BaseModel):
    id: int
    zone_type: str # red | yellow | green
    hazard_type: str
    confidence: Optional[float] = None
    population: int
    reason: Optional[str] = None
    valid_from: datetime
    source: str
    geometry: Dict[str, Any]

class PopulationSummaryResponse(BaseModel):
    hazard_type: str
    red_population: int
    yellow_population: int
    green_population: int
    total_population: int
    vulnerable_groups: Dict[str, int]
    timestamp: datetime

# Facility Schemas
class FacilityResponse(BaseModel):
    id: int
    type: str # hospital | shelter | fire_station | police_station
    name: str
    lat: float
    lon: float
    capacity: Optional[int] = None
    beds_available: Optional[int] = None
    status: str
    contact: Optional[str] = None
    distance_km: Optional[float] = None
    eta_minutes: Optional[float] = None
    in_red_zone: bool = False

# Routing Schemas
class RouteRequest(BaseModel):
    origin: List[float] # [lon, lat]
    destination: List[float] # [lon, lat]
    vehicle_type: str = "ambulance" # ambulance, truck, boat, foot
    avoid_hazards: bool = True

class RouteResponse(BaseModel):
    distance_km: float
    duration_min: float
    hazard_avoided: bool
    risk_rating: str # low, moderate, high
    route_geometry: LineStringGeometry
    confidence: str # high, low

# Dispatch Schemas
class DispatchCreate(BaseModel):
    sos_ids: List[UUID]
    vehicle_id: Optional[int] = None
    facility_id: Optional[int] = None
    batch: bool = False

class DispatchResponse(BaseModel):
    id: int
    sos_ids: List[UUID]
    batch: bool
    vehicle_id: Optional[int] = None
    facility_id: Optional[int] = None
    status: str
    created_at: datetime
    updated_at: datetime
    route_geometry: Optional[Dict[str, Any]] = None
    alerts_dispatched: Dict[str, Any]

# Road Report
class RoadReportCreate(BaseModel):
    segment_id: Optional[str] = None
    status: str # blocked | clear
    reporter: Optional[str] = "volunteer"
    photo_url: Optional[str] = None
    lat: float
    lon: float

class RoadReportResponse(BaseModel):
    id: int
    segment_id: Optional[str] = None
    status: str
    reporter: Optional[str] = None
    photo_url: Optional[str] = None
    lat: float
    lon: float
    at: datetime

    class Config:
        from_attributes = True
