import logging
from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        # In-memory mock notification store for inspection/testing during hackathon demo
        self.sent_notifications: List[Dict[str, Any]] = []

    async def notify_volunteers_nearby(
        self,
        sos_id: UUID,
        severity: str,
        lat: float,
        lon: float,
        radius_km: float = 5.0
    ):
        """Notifies volunteers within 5km radius. Red triggers urgent sound alert."""
        message = {
            "type": "volunteer_alert",
            "sos_id": str(sos_id),
            "severity": severity,
            "sound": "siren" if severity.lower() == "red" else "silent",
            "urgent": severity.lower() == "red",
            "lat": lat,
            "lon": lon,
            "radius_km": radius_km,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.sent_notifications.append(message)
        logger.info(f"[NOTIFY] Volunteer alert sent: {message}")
        return message

    async def send_transport_alert(
        self,
        vehicle_contact: str,
        provider_name: str,
        sos_level: str,
        pickup_lat: float,
        pickup_lon: float,
        destination_name: str,
        people_count: int,
        route_info: Optional[Dict[str, Any]] = None
    ):
        """Sends push/SMS to vehicle provider. Red alerts marked URGENT."""
        urgent_tag = "[URGENT] " if sos_level.lower() == "red" else ""
        text = (
            f"{urgent_tag}Disastra Transport Dispatch: Pickup {people_count} people "
            f"at ({pickup_lat:.4f}, {pickup_lon:.4f}) -> {destination_name}. "
            f"Level: {sos_level.upper()}."
        )
        alert = {
            "channel": "SMS/Push",
            "recipient": vehicle_contact,
            "provider": provider_name,
            "urgent": sos_level.lower() == "red",
            "message": text,
            "route_info": route_info,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.sent_notifications.append(alert)
        logger.info(f"[DISPATCH NOTIFICATION] Sent to {vehicle_contact}: {text}")
        return alert

    async def pre_alert_hospital(
        self,
        hospital_contact: str,
        hospital_name: str,
        sos_level: str,
        patient_count: int,
        eta_minutes: float
    ):
        """Pre-alerts hospital with patient count, SOS level, and ETA (F6.6)."""
        text = (
            f"Disastra Pre-Alert for {hospital_name}: Inbound {patient_count} patient(s), "
            f"Severity: {sos_level.upper()}, ETA: {eta_minutes:.1f} min."
        )
        alert = {
            "channel": "Hospital_Direct",
            "recipient": hospital_contact,
            "hospital": hospital_name,
            "message": text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.sent_notifications.append(alert)
        logger.info(f"[HOSPITAL PRE-ALERT] {text}")
        return alert

    async def send_sms_response(self, phone_number: str, message: str):
        """Mock SMS gateway outbound response."""
        record = {
            "channel": "SMS",
            "to": phone_number,
            "text": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.sent_notifications.append(record)
        logger.info(f"[SMS OUT] To {phone_number}: {message}")
        return record

notify_service = NotificationService()
