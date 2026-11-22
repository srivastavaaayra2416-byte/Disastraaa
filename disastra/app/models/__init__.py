from app.models.enums import SeverityEnum, SOSStatusEnum

try:
    from app.models.entities import (
        SOSRequest, SOSEventLog, ZoneCell, Facility, Vehicle, Dispatch, RoadReport
    )
except Exception:
    # Allows lightweight testing and environments without PostGIS C-extensions loaded
    pass
