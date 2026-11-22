import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, BigInteger, Enum, Text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from geoalchemy2 import Geometry
from app.core.database import Base
from app.models.enums import SeverityEnum, SOSStatusEnum

class SOSRequest(Base):
    __tablename__ = "sos_request"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_msg_id = Column(String, nullable=False)
    device_id = Column(String, nullable=False)
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    accuracy_m = Column(Float, nullable=True)
    severity = Column(Enum(SeverityEnum, name="severity", create_type=False), nullable=False)
    severity_changed_by = Column(String, nullable=True)  # victim | control_room | system
    severity_changed_at = Column(DateTime(timezone=True), nullable=True)
    severity_reason = Column(String, nullable=True)
    need_type = Column(String, nullable=True)  # MED, TRAP, FOOD, EVAC, OTHER
    people_count = Column(Integer, default=1)
    battery_pct = Column(Integer, nullable=True)
    channel = Column(String, nullable=True)  # internet | sms | mesh | gateway
    status = Column(Enum(SOSStatusEnum, name="sos_status", create_type=False), nullable=False, default=SOSStatusEnum.received)
    priority_score = Column(Integer, nullable=False)
    zone_type = Column(String, nullable=True)  # red | yellow | green
    has_children = Column(Boolean, default=False)
    has_elderly = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

class SOSEventLog(Base):
    __tablename__ = "sos_event_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sos_id = Column(UUID(as_uuid=True), ForeignKey("sos_request.id", ondelete="CASCADE"), nullable=False)
    event = Column(String, nullable=False)  # created, relayed, received, acknowledged, upgraded, relabelled, escalated, cancelled, closed
    actor = Column(String, nullable=False)
    detail = Column(JSONB, nullable=True)
    at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class ZoneCell(Base):
    __tablename__ = "zone_cell"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    geometry = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)
    zone_type = Column(String, nullable=False)  # red | yellow | green
    hazard_type = Column(String, nullable=False, default="flood")
    confidence = Column(Float, nullable=True)
    population = Column(Integer, default=0)
    reason = Column(Text, nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    source = Column(String, nullable=False)

class Facility(Base):
    __tablename__ = "facility"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    type = Column(String, nullable=False)  # hospital, shelter, fire_station, police_station
    name = Column(String, nullable=False)
    geometry = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    capacity = Column(Integer, nullable=True)
    beds_available = Column(Integer, nullable=True)
    status = Column(String, default="open")  # open, damaged, etc.
    contact = Column(String, nullable=True)

class Vehicle(Base):
    __tablename__ = "vehicle"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    type = Column(String, nullable=False)  # ambulance, bus, boat, truck, tractor
    capacity = Column(Integer, nullable=False)
    provider = Column(String, nullable=False)
    contact = Column(String, nullable=False)
    status = Column(String, nullable=False, default="available")  # available, busy, maintenance, offline
    last_location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

class Dispatch(Base):
    __tablename__ = "dispatch"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sos_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False)
    batch = Column(Boolean, default=False)
    vehicle_id = Column(BigInteger, ForeignKey("vehicle.id"), nullable=True)
    facility_id = Column(BigInteger, ForeignKey("facility.id"), nullable=True)
    route_geometry = Column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=True)
    status = Column(String, nullable=False, default="draft")  # draft, dispatched, accepted, declined, en_route, completed, cancelled
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

class RoadReport(Base):
    __tablename__ = "road_report"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    segment_id = Column(String, nullable=True)
    status = Column(String, nullable=False)  # blocked | clear
    reporter = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    at = Column(DateTime(timezone=True), default=datetime.utcnow)
