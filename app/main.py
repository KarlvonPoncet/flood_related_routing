from __future__ import annotations

from app.data.flood_api import MockFloodAdapter
from app.services.shipment_service import ShipmentService


def main() -> None:
    service = ShipmentService(source_adapter=MockFloodAdapter())
    route = [(52.45, 13.25), (52.55, 13.55)]
    result = service.evaluate_route(route_id="demo-route", polyline=route)
    print(result)


if __name__ == "__main__":
    main()

