import enum

class SeverityEnum(str, enum.Enum):
    red = "red"
    yellow = "yellow"

class SOSStatusEnum(str, enum.Enum):
    pending = "pending"
    relayed = "relayed"
    received = "received"
    acknowledged = "acknowledged"
    in_progress = "in_progress"
    closed = "closed"
    cancelled = "cancelled"
