# Disastra frontend

The existing citizen and command-room views are retained and upgraded in place. FastAPI serves this folder at the site root when it is present, so the UI calls the backend on the same origin.

Run the complete local stack from the repository root with `docker compose up --build`, then open `http://localhost:8000/`. The API docs remain at `http://localhost:8000/docs`. Use the API field in the top bar only when the backend is hosted at another address.

## Connected capabilities

- Leaflet map with OpenStreetMap road tiles, panning/zoom, selectable location, backend GeoJSON hazard zones, SOS, facilities, vehicles, road reports, route overlays, and OSM attribution.
- REST integration with `/health`, `/v1/sos`, `/v1/zones`, `/v1/population`, `/v1/facilities/nearest`, `/v1/route`, `/v1/dispatch`, `/v1/dispatch/vehicles`, and `/v1/road-report`; requests refresh every 15 seconds.
- Red SOS is stored locally with a stable client message ID when the API is unavailable, then retried idempotently. Yellow SOS need and people count are sent to the API. Control-room upgrades and re-labels call the backend severity endpoint.
- Baseline and hazard-avoidance routes are requested from the backend. The current route service uses a straight-line distance and geometric detour heuristic, not a road-network router; displayed travel estimates are not turn-by-turn navigation. Dispatch and Yellow batch actions are posted to the backend. Red-zone facilities are excluded from safe dispatch options.
- Existing citizen Red countdown, cancel confirmation, Yellow need form, status panel, and command-room controls remain in the UI. An unsupported operation is labelled rather than simulated as backend state.
- Browser app shell caching is enabled; API responses are never cached. OSM tiles, satellite imagery, and regional offline map data are not bundled.

## Data, map, and security boundaries

This is a browser PWA, not a native Android app. OSM is a real standard street map; no satellite imagery provider is configured, so the satellite layer control remains unavailable. Satellite Intelligence displays only backend zone-source metadata and record timestamps. The repository's `geo/seed_demo_data.py` contains a Kerala 2018 demonstration scenario; those seeded rows are not current disaster observations.

SMS and nearby-phone/Bluetooth mesh transport are not implemented by this frontend. The API's `/ws/dashboard` endpoint currently echoes client messages; it does not stream SOS events, so the dashboard polls REST every 15 seconds instead. The backend currently uses the `X-User-Role` request header and wildcard CORS configuration without real authentication. Keep this stack local/trusted until proper identity and authorization are added; the frontend's control-room header does not provide security. No real emergency service is contacted by this demo.
