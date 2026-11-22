from datetime import datetime, timezone
from typing import Optional

def minutes_waiting(created_at: datetime, now: Optional[datetime] = None) -> int:
    """Calculates minutes elapsed between created_at and now."""
    if now is None:
        now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    
    diff = (now - created_at).total_seconds()
    return max(0, int(diff // 60))

def compute_priority_score(
    severity: str,
    need_type: Optional[str] = None,
    has_children: bool = False,
    has_elderly: bool = False,
    zone_type: Optional[str] = None,
    battery_pct: Optional[int] = None,
    created_at: Optional[datetime] = None,
    now: Optional[datetime] = None
) -> int:
    """
    Computes priority score based on PRD / Guidelines Section 6:
    Base score: Red = 100, Yellow = 40.
    Factors:
    - need_type == 'MED' (+15)
    - has_children or has_elderly (+10)
    - zone_type == 'red' (+10)
    - battery_pct is not None and battery_pct < 15 (+8)
    - minutes_waiting: capped waiting bonus min(20, minutes_waiting // 5)
    """
    score = 100 if severity.lower() == "red" else 40
    
    if need_type and need_type.upper() in ["MED", "MEDS"]:
        score += 15
        
    if has_children or has_elderly:
        score += 10
        
    if zone_type and zone_type.lower() == "red":
        score += 10
        
    if battery_pct is not None and battery_pct < 15:
        score += 8
        
    if created_at is not None:
        waiting = minutes_waiting(created_at, now)
        score += min(20, waiting // 5)
        
    return score
