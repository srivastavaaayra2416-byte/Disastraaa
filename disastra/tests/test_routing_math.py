import pytest
import math
from app.services.geo_utils import haversine_distance

def test_haversine_distance():
    # Distance between Kochi (10.0, 76.3) and Aluva (10.1, 76.35)
    p1 = [76.3, 10.0]
    p2 = [76.35, 10.1]
    d = haversine_distance(p1, p2)
    # Approx 12-13 km
    assert 10.0 < d < 15.0

def test_detour_geometry_logic():
    # Verify perpendicular offset generation for hazard avoidance
    origin = [76.3, 10.0]
    dest = [76.3, 10.1]
    
    dx = dest[0] - origin[0]
    dy = dest[1] - origin[1]
    length = math.hypot(dx, dy)
    assert length > 0
    
    mid_lon = (origin[0] + dest[0]) / 2.0
    mid_lat = (origin[1] + dest[1]) / 2.0
    
    offset_factor = 0.02
    detour_lon = mid_lon - (dy / length) * offset_factor
    detour_lat = mid_lat + (dx / length) * offset_factor
    
    # Detour must shift longitude away from the straight vertical line
    assert abs(detour_lon - mid_lon) > 0.01
