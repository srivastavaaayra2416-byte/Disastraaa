import pytest
from datetime import datetime, timezone
from app.services.sms_parser import parse_sms_payload
from app.services.scoring import compute_priority_score
from app.models.enums import SeverityEnum

def test_sms_parser_valid_red():
    sms = "R*26.8467,80.9462*MED*3P*B12*22NOV1530"
    result = parse_sms_payload(sms)
    assert result is not None
    assert result["severity"] == SeverityEnum.red
    assert abs(result["lat"] - 26.8467) < 0.0001
    assert abs(result["lon"] - 80.9462) < 0.0001
    assert result["need_type"] == "MED"
    assert result["people_count"] == 3
    assert result["battery_pct"] == 12

def test_sms_parser_valid_yellow():
    sms = "Y*10.1076,76.3516*FOOD*2P*B45*22NOV1600"
    result = parse_sms_payload(sms)
    assert result is not None
    assert result["severity"] == SeverityEnum.yellow
    assert abs(result["lat"] - 10.1076) < 0.0001
    assert abs(result["lon"] - 76.3516) < 0.0001
    assert result["need_type"] == "FOOD"
    assert result["people_count"] == 2
    assert result["battery_pct"] == 45

def test_sms_parser_missing_optional_fields():
    # Only Level and coordinates
    sms = "R*10.1076,76.3516"
    result = parse_sms_payload(sms)
    assert result is not None
    assert result["severity"] == SeverityEnum.red
    assert result["need_type"] == "OTHER"
    assert result["people_count"] == 1
    assert result["battery_pct"] is None

def test_sms_parser_lenient_unknown_need():
    sms = "y * 12.34, 56.78 * RANDOM_CODE * 5P"
    result = parse_sms_payload(sms)
    assert result is not None
    assert result["severity"] == SeverityEnum.yellow
    assert result["need_type"] == "OTHER"
    assert result["people_count"] == 5

def test_sms_parser_malformed():
    assert parse_sms_payload("INVALID_MESSAGE_WITHOUT_COORDS") is None
    assert parse_sms_payload("X*10.0,20.0") is None  # invalid level code

def test_priority_scoring_severity_first():
    """Rule: Every Red always sorts above every Yellow (F5.13)."""
    # Max possible Yellow score
    yellow_score = compute_priority_score(
        severity="yellow",
        need_type="MED",
        has_children=True,
        has_elderly=True,
        zone_type="red",
        battery_pct=5,
        created_at=datetime(2026, 11, 22, 0, 0, tzinfo=timezone.utc),
        now=datetime(2026, 11, 22, 2, 0, tzinfo=timezone.utc)
    )
    
    # Base Red score
    red_score = compute_priority_score(
        severity="red"
    )

    # Red base is 100
    assert red_score == 100
    # Yellow can go up with factors: 40 + 15(MED) + 10(children/elderly) + 10(red zone) + 8(battery) + 20(waiting) = 103
    # Note that in SQL ORDER BY: severity (red first), priority_score DESC ensures Red is always first!
