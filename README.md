# Disastra — Space-Based Disaster Management and Rescue Platform

Space-Based Disaster Management and Rescue Platform Backend based on PRD v1.1 and Backend Guidelines.

## Architecture & Features Built
- **Dual-Level SOS Ingestion Engine (`POST /v1/sos`)**: Supports Internet, Bluetooth Mesh relay, LoRa/Satellite gateways, and SMS webhook with sub-160 char lenient SMS parser (`R*lat,lon*need*people*battery*timestamp`).
- **Severity-First Ordering & Priority Scoring (F5.13, F5.14)**: Every Red alert sorts before any Yellow alert. Priority factors: medical needs, children, elderly, red zone location, low battery (<15%), and waiting time bonus.
- **Dynamic Deduplication & Upgrade (F5.12, F5.6)**: 1 active Red and 1 active Yellow per device. Incoming Red automatically upgrades an active Yellow. `PATCH /v1/sos/{id}/severity` handles victim upgrades, confirm-guarded downgrades, and mandatory reason control-room relabeling with event logging.
- **Zoning & Population Impact (`GET /v1/zones`, `GET /v1/population`)**: Classifies 100m-500m cells into Red, Yellow, Green zones with source freshness and explainability reasons (`reason`). Computes population at risk and vulnerable groups.
- **Hazard-Aware Safe Routing (`POST /v1/route`)**: Computes safe rescue and evacuation routes avoiding flooded red zones and blocked roads reported by crowd volunteers.
- **Safe Facility Search (`GET /v1/facilities/nearest`)**: Locates nearest hospitals, shelters, and fire stations by route time while automatically flagging and excluding compromised facilities located in Red zones (F6.4).
- **Transport Registry & Dispatch (`POST /v1/dispatch`, `GET /v1/dispatch/vehicles`)**: One-tap fast lane dispatch for Red emergencies, yellow batching, automatic pre-alerts to destination hospitals (F6.6), and provider SMS/push notifications marked URGENT (F8.3).
- **Escalation Background Worker (`app/workers/escalation_worker.py`)**: Idempotent state machine that flags unacknowledged Red (>2 min) for re-broadcast, and raises Yellow (>30 min, battery <10%, turns Red zone, or 3+ cluster) for urgent Red review.
- **Real-Time WebSockets (`/ws/dashboard`, `/ws/volunteers`) & Redis Pub/Sub**: Pushes instantaneous queue re-sorts and volunteer siren alerts.
- **Privacy & Safeguards (F4.7, F5.15)**: Location fuzzing for public views, precise coordinates for authorized responders, and rate limiting for Red alerts.

## Project Structure
```
disastra-backend/
├── app/
│   ├── api/             # Routers: sos, zones, facilities, route, dispatch, road_reports, websockets
│   ├── core/            # Configuration, database engine, Redis pub/sub & rate limiting
│   ├── models/          # PostGIS SQLAlchemy entities & enums
│   ├── schemas/         # Pydantic v2 request/response schemas
│   ├── services/        # sos_service, scoring, routing, facility, dispatch, notify, sms_parser
│   ├── workers/         # escalation_worker (Section 7)
│   └── main.py          # FastAPI application entrypoint
├── geo/                 # seed_demo_data.py (Kerala 2018 hero scenario)
├── migrations/          # 001_init.sql PostGIS database schema
├── tests/               # pytest test suite
├── docker-compose.yml   # Multi-service setup (api, worker, postgis, redis)
├── Dockerfile           # Python 3.11 + GDAL container definition
└── requirements.txt
```

## Frontend
The existing citizen and command-room interface is in `frontend/`. FastAPI serves it from `http://localhost:8000/` when present. See [`frontend/README.md`](frontend/README.md) for the map, API integration, live-data boundaries, and security notes. The mapping library loads from Leaflet CDN and map tiles use OpenStreetMap with attribution.

## Running with Docker Compose (Recommended)
```bash
docker compose up --build
```
This starts:
- `api` at `http://localhost:8000` (Swagger UI at `http://localhost:8000/docs`)
- `worker` running the background escalation engine
- `postgres` (PostGIS 16-3.4) on port `5432` with automatic table initialization (`001_init.sql`)
- `redis` (Redis 7) on port `6379`
