import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.models.enums import SeverityEnum

# Format: R*26.8467,80.9462*MED*3P*B12*22NOV1530
# level * lat,lon * need * people * battery * timestamp
SMS_PATTERN = re.compile(
    r"^(?P<level>[RY])\*(?P<lat>-?\d+(?:\.\d+)?),(?P<lon>-?\d+(?:\.\d+)?)"
    r"(?:\*(?P<need>[A-Za-z]+))?"
    r"(?:\*(?P<people>\d+)P)?"
    r"(?:\*B(?P<battery>\d+))?"
    r"(?:\*(?P<timestamp>[0-9A-Za-z]+))?$",
    re.IGNORECASE
)

VALID_NEEDS = {"MED", "TRAP", "FOOD", "EVAC", "MEDS", "OTHER"}

def parse_sms_payload(payload_str: str) -> Optional[Dict[str, Any]]:
    """
    Parses compact SMS emergency payload according to Section 5.2.
    Example: R*26.8467,80.9462*MED*3P*B12*22NOV1530
    Lenient rules:
    - Trim whitespace, lowercase accepted.
    - First char R or Y sets severity.
    - Need codes fallback to OTHER if unknown.
    - Defaults people to 1 if missing.
    - Never discard valid coordinates even if other fields are broken.
    """
    if not payload_str or not isinstance(payload_str, str):
        return None
        
    trimmed = payload_str.strip()
    if not trimmed:
        return None

    # Lenient fallback if format is slightly irregular but coordinates exist:
    parts = [p.strip() for p in trimmed.split("*") if p.strip()]
    if not parts:
        return None

    first_char = parts[0][0].upper()
    if first_char not in ("R", "Y"):
        return None  # Only R or Y accepted as severity level

    severity = SeverityEnum.red if first_char == "R" else SeverityEnum.yellow

    if len(parts) < 2:
        return None

    coord_part = parts[1]
    if "," not in coord_part:
        return None

    try:
        lat_str, lon_str = coord_part.split(",", 1)
        lat = float(lat_str.strip())
        lon = float(lon_str.strip())
    except ValueError:
        return None

    need_type = "OTHER"
    people_count = 1
    battery_pct = None
    created_at = datetime.now(timezone.utc)

    # Process remaining parts leniently
    for part in parts[2:]:
        p_up = part.upper()
        if p_up in VALID_NEEDS:
            need_type = p_up
        elif p_up.endswith("P") and p_up[:-1].isdigit():
            people_count = int(p_up[:-1])
        elif p_up.startswith("B") and p_up[1:].isdigit():
            battery_pct = int(p_up[1:])
        elif len(p_up) >= 9:
            # Try parsing timestamp format e.g. 22NOV1530 or ISO
            try:
                # Mock year as current year
                curr_year = datetime.now(timezone.utc).year
                dt = datetime.strptime(f"{p_up}{curr_year}", "%d%b%H%M%Y")
                created_at = dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass

    return {
        "severity": severity,
        "lat": lat,
        "lon": lon,
        "need_type": need_type,
        "people_count": people_count,
        "battery_pct": battery_pct,
        "created_at": created_at
    }
