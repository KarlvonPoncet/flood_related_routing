# Spezifikation: Data Layer für Flood-Aware Rerouting (Hackathon)

## 1. Zielbild
Der Data Layer liefert einheitliche, zeitnahe Flutinformationen aus Copernicus-nahen Quellen für das Routing-System.
Er soll:
- Geodaten laden und normalisieren
- Risiko-Scores für Straßensegmente/Route-Abschnitte bereitstellen
- Schnelle Abfragen für die Decision Engine ermöglichen
- Im Hackathon robust mit unvollständigen/verspäteten Daten umgehen

## 2. Architektur (Data Layer)

### 2.1 Schichten
1. Ingestion
- Adapter für externe Quellen (z. B. Copernicus EMS-Mappings, Sentinel-basierte Flood-Layer, optional Wetter/Nowcast).
- Pull-basiert (Intervall) plus manuelle Trigger.

2. Normalisierung
- Vereinheitlichung auf gemeinsames Geo-Schema (WGS84 / EPSG:4326).
- Umwandlung in ein gemeinsames `FloodEvent`- und Raster/Vektor-Format.
- Quality Flags (source_confidence, data_age_minutes, geometry_quality).

3. Speicherung
- Hot Store: schnelles Lesen für aktuelle Entscheidungen (z. B. GeoJSON + In-Memory Cache).
- Optional Persistenz: PostGIS/SQLite für Verlauf und Reproduzierbarkeit.

4. Serving
- Interne API für `risk_calculator.py`:
  - Risiko für Punkt
  - Risiko entlang Polyline
  - Betroffene Segmente in Bounding Box

### 2.2 Laufzeit-Datenfluss
1. Scheduler ruft Source Adapter auf.
2. Adapter lädt neue Flood-Datensätze.
3. Loader normalisiert und validiert.
4. Data Store aktualisiert Hot-Daten + Index.
5. Risk Calculator fragt Risiko je Route-Abschnitt ab.
6. Decision Engine entscheidet `keep_route` vs `reroute`.

## 3. Datenquellen (Copernicus-fokussiert)

## 3.1 Primär
- Copernicus Emergency Management Service (EMS): Flood extent / delineation layers.
- Sentinel-basierte Überflutungsindikatoren (falls im Hackathon-Datensatz enthalten).

## 3.2 Sekundär (Fallback)
- Historische Flood-Polygone (statisch) für Baseline-Risiko.
- Optional lokale Wetter-/Niederschlagsfeeds als kurzfristiger Proxy.

## 3.3 Source-Priorisierung
- `priority=1`: Aktuelle Copernicus Event-Layer
- `priority=2`: Sentinel-derived near-real-time Layer
- `priority=3`: Historische/Fallback-Layer

Bei Konflikten gewinnt die Quelle mit höherer Priorität und jüngerer `observation_time`.

## 4. Datenmodell

## 4.1 Kernentitäten
1. `FloodEvent`
- `event_id: str`
- `source: str`
- `observation_time: datetime`
- `ingested_at: datetime`
- `severity: float (0..1)`
- `confidence: float (0..1)`
- `geometry: Polygon | MultiPolygon`
- `properties: dict`

2. `FloodTile` (optional bei Rasteransatz)
- `tile_id: str`
- `bbox: tuple[min_lon, min_lat, max_lon, max_lat]`
- `risk_value: float (0..1)`
- `resolution_m: int`
- `valid_from`, `valid_to`

3. `RouteRiskSegment`
- `segment_id: str`
- `route_id: str`
- `geometry: LineString`
- `risk_score: float (0..1)`
- `risk_reason: list[str]`

## 4.2 Interne Standardform
- CRS: EPSG:4326
- Zeit: UTC ISO-8601
- Risiko: normalisiert 0..1
- Unsicherheit separat führen (`confidence`), nicht in `risk_score` verstecken

## 5. Schnittstellen im bestehenden Code

## 5.1 `app/data/flood_api.py`
Verantwortung:
- Source Adapter Interface
- Konkrete Adapter (`CopernicusEMSAdapter`, `MockFloodAdapter`)

Methoden:
- `fetch_events(bbox, since) -> list[FloodEvent]`
- `health() -> SourceStatus`

## 5.2 `app/data/loader.py`
Verantwortung:
- Parsing, Normalisierung, Validierung, Deduplizierung

Methoden:
- `normalize(raw_event) -> FloodEvent`
- `validate(event) -> bool`
- `merge(events) -> list[FloodEvent]`

## 5.3 `app/logic/risk_calculator.py`
Verantwortung:
- Geometrischer Overlay von Route und Flood-Geometrien
- Aggregation zu Segment- und Gesamtrisikowerten

Methoden:
- `risk_for_point(lat, lon, at_time) -> RiskResult`
- `risk_for_polyline(polyline, at_time) -> list[RouteRiskSegment]`

## 5.4 `app/services/shipment_service.py`
Verantwortung:
- Orchestrierung: Route laden, Risiken berechnen, Empfehlung zurückgeben

Output:
- `decision`: `keep_route` | `reroute`
- `risk_summary`: max/avg risk + betroffene Segmente
- `explainability`: wichtigste FloodEvents, Data Age

## 6. Implementierungsplan (Hackathon-tauglich)

## Phase 0: Setup (0.5 Tag)
- Projektstruktur unter `app/data` finalisieren.
- Konfigurationsdatei für Quellen + Polling-Intervall.
- Mock-Datensatz für Offline-Entwicklung.

## Phase 1: Ingestion MVP (1 Tag)
- Adapter-Interface + `MockFloodAdapter` implementieren.
- Ersten Copernicus-Adapter (minimal) implementieren.
- Rohdaten als GeoJSON lokal cachen.

## Phase 2: Normalisierung + Speicherung (1 Tag)
- Einheitliches `FloodEvent`-Schema.
- Validator + Dedupe (event_id + geometry hash + time bucket).
- In-Memory Index nach BBox.

## Phase 3: Risiko-Berechnung (1 Tag)
- Spatial Intersection Route-Segment vs Flood-Polygone.
- Score-Formel implementieren:
  - `risk = w1*severity + w2*coverage + w3*recency_factor`
- Grenzwerte definieren:
  - `risk < 0.35`: keep
  - `0.35..0.6`: warn
  - `> 0.6`: reroute

## Phase 4: Service-Integration + Demo (0.5-1 Tag)
- `shipment_service` koppeln.
- CLI/Testcases: normale Route, teilweise überflutet, vollständig blockiert.
- Demo-Ausgabe mit Begründung und Datenalter.

## 7. Nicht-funktionale Anforderungen
- Latenz Risikoabfrage: Ziel < 300 ms pro Route (MVP, lokale Daten).
- Resilienz: bei Source-Fehler auf letzte gültige Daten + Warnflag.
- Nachvollziehbarkeit: jede Entscheidung mit Event-IDs und Timestamps.
- Reproduzierbarkeit: optional Snapshots je Demo-Run.

## 8. Teststrategie
- Unit Tests:
  - Normalisierung, CRS-Konvertierung, Dedupe
  - Risk-Formel und Grenzfälle
- Integration Tests:
  - End-to-End von `fetch_events` bis `decision_engine`
- Szenarien:
  - Keine Flood-Daten
  - Alte Flood-Daten (`data_age` > Schwelle)
  - Konflikt zwischen Quellen

## 9. Risiken und Gegenmaßnahmen
- Uneinheitliche Quelldaten: striktes Normalisierungsschema + Validator.
- Geringe Aktualität: `data_age` sichtbar machen und in Entscheidung einfließen lassen.
- Geometriefehler: vereinfachte Reparatur (buffer(0)-Strategie) + Fallback ignore mit Logging.
- Zu hohe Komplexität: Raster-Ansatz zunächst optional halten, Vektor-MVP priorisieren.

## 10. Konkrete nächste Umsetzungsschritte im Repo
1. `app/data/flood_api.py`: Adapter-Interface + Mock-Implementierung.
2. `app/models/flood_event.py`: finalen Dataclass/Pydantic-Typ definieren.
3. `app/data/loader.py`: `normalize/validate/merge` implementieren.
4. `app/logic/risk_calculator.py`: Overlay + Score-Formel bauen.
5. `tests/`: 3 Kernszenarien für Entscheidung `keep/warn/reroute`.

