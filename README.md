flood-routing-system/
│
├── app/
│   ├── main.py                  # Einstiegspunkt (Tests / CLI)
│   │
│   ├── data/
│   │   ├── flood_api.py        # Datenquelle (API/Mock)
│   │   ├── loader.py           # Daten normalisieren
│   │
│   ├── models/
│   │   ├── location.py         # Koordinaten / Regionen
│   │   ├── route.py            # Lieferroute
│   │   ├── shipment.py         # Transportgut
│   │   ├── flood_event.py      # Flutdatenmodell
│   │
│   ├── logic/
│   │   ├── risk_calculator.py  # Flutrisiko berechnen
│   │   ├── cost_calculator.py  # Kosten (Umweg vs Risiko)
│   │   ├── decision_engine.py  # Entscheidung (route / reroute)
│   │
│   ├── services/
│   │   ├── shipment_service.py # zentrale API für dein System
│   │
│   ├── utils/
│   │   ├── geo.py              # Distanz, Geodaten
│   │   ├── config.py
│
├── tests/
├── requirements.txt
└── README.md
