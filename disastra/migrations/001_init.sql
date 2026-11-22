CREATE EXTENSION IF NOT EXISTS postgis;

DO $$ BEGIN
    CREATE TYPE severity AS ENUM ('red', 'yellow');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE sos_status AS ENUM (
        'pending', 'relayed', 'received', 'acknowledged', 'in_progress', 'closed', 'cancelled'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS sos_request (
    id UUID PRIMARY KEY,
    client_msg_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    location geometry(Point, 4326) NOT NULL,
    accuracy_m REAL,
    severity severity NOT NULL,
    severity_changed_by TEXT,
    severity_changed_at TIMESTAMPTZ,
    severity_reason TEXT,
    need_type TEXT,
    people_count INT DEFAULT 1,
    battery_pct INT,
    channel TEXT,
    status sos_status NOT NULL DEFAULT 'received',
    priority_score INT NOT NULL,
    zone_type TEXT,
    has_children BOOLEAN DEFAULT false,
    has_elderly BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at TIMESTAMPTZ,
    UNIQUE (device_id, client_msg_id)
);

CREATE INDEX IF NOT EXISTS idx_sos_request_location ON sos_request USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_sos_request_priority ON sos_request (severity, priority_score DESC, received_at ASC);
CREATE INDEX IF NOT EXISTS idx_sos_request_device_status ON sos_request (device_id, status);

CREATE TABLE IF NOT EXISTS sos_event_log (
    id BIGSERIAL PRIMARY KEY,
    sos_id UUID REFERENCES sos_request(id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    actor TEXT NOT NULL,
    detail JSONB,
    at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS zone_cell (
    id BIGSERIAL PRIMARY KEY,
    geometry geometry(Polygon, 4326) NOT NULL,
    zone_type TEXT NOT NULL, -- red | yellow | green
    hazard_type TEXT NOT NULL, -- flood, fire, landslide...
    confidence REAL,
    population INT,
    reason TEXT,
    valid_from TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_zone_cell_geom ON zone_cell USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_zone_cell_type ON zone_cell (zone_type, hazard_type);

CREATE TABLE IF NOT EXISTS facility (
    id BIGSERIAL PRIMARY KEY,
    type TEXT NOT NULL, -- hospital, shelter, fire_station, police_station
    name TEXT NOT NULL,
    geometry geometry(Point, 4326) NOT NULL,
    capacity INT,
    beds_available INT,
    status TEXT DEFAULT 'open',
    contact TEXT
);

CREATE INDEX IF NOT EXISTS idx_facility_geom ON facility USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_facility_type ON facility (type);

CREATE TABLE IF NOT EXISTS vehicle (
    id BIGSERIAL PRIMARY KEY,
    type TEXT NOT NULL, -- ambulance, bus, boat, truck, tractor
    capacity INT NOT NULL,
    provider TEXT NOT NULL,
    contact TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available', -- available, busy, maintenance, offline
    last_location geometry(Point, 4326)
);

CREATE INDEX IF NOT EXISTS idx_vehicle_geom ON vehicle USING GIST (last_location);

CREATE TABLE IF NOT EXISTS dispatch (
    id BIGSERIAL PRIMARY KEY,
    sos_ids UUID[] NOT NULL,
    batch BOOLEAN DEFAULT false,
    vehicle_id BIGINT REFERENCES vehicle(id),
    facility_id BIGINT REFERENCES facility(id),
    route_geometry geometry(LineString, 4326),
    status TEXT NOT NULL DEFAULT 'draft', -- draft, dispatched, accepted, declined, en_route, completed, cancelled
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS road_report (
    id BIGSERIAL PRIMARY KEY,
    segment_id TEXT,
    status TEXT NOT NULL, -- blocked | clear
    reporter TEXT,
    photo_url TEXT,
    location geometry(Point, 4326) NOT NULL,
    at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_road_report_geom ON road_report USING GIST (location);
