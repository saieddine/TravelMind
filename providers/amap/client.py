
from providers.config import environment_file
import os
import requests

from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(environment_file())


class AmapClient:
    BASE_URL = "https://restapi.amap.com/v3"

    CATEGORIES = {
        "museum": ("140100", "1401"),
        "attraction": ("110000", "11"),
        "restaurant": ("050000", "05"),
        "hotel": ("100000", "10"),
    }

    def __init__(self):
        self.api_key = os.getenv("AMAP_API_KEY")

        if not self.api_key:
            raise ValueError(
                "Missing AMAP_API_KEY in .env"
            )

    def _request(self, endpoint, params):
        params = dict(params)
        params["key"] = self.api_key
        params["output"] = "JSON"

        try:
            response = requests.get(
                self.BASE_URL + endpoint,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()

        except requests.RequestException as error:
            raise RuntimeError(
                f"Amap connection failed: "
                f"{type(error).__name__}"
            ) from None

        if data.get("status") != "1":
            raise RuntimeError(
                f"Amap API error: {data.get('info')} "
                f"({data.get('infocode')})"
            )

        return data

    @staticmethod
    def _coordinates(location):
        if not isinstance(location, str):
            return None

        try:
            lon, lat = map(float, location.split(","))

            return {
                "longitude": lon,
                "latitude": lat,
                "system": "GCJ-02"
            }
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _clean(value):
        return value if isinstance(value, str) else None

    def search_places(
        self,
        city,
        category="attraction",
        keyword=None,
        limit=10
    ):
        if category not in self.CATEGORIES:
            raise ValueError(
                f"Unsupported category: {category}"
            )

        type_code, type_prefix = self.CATEGORIES[category]

        params = {
            "city": city,
            "citylimit": "true",
            "types": type_code,
            "offset": max(1, min(limit, 25)),
            "page": 1,
            "extensions": "base"
        }

        if keyword:
            params["keywords"] = keyword

        data = self._request("/place/text", params)

        results = []
        retrieved_at = datetime.now(
            timezone.utc
        ).isoformat()

        for poi in data.get("pois", []):
            poi_type = str(poi.get("typecode", ""))

            # Exclude clearly unrelated POI categories
            codes = poi_type.split("|")
            if not any(
                code.startswith(type_prefix)
                for code in codes
            ):
                continue

            place = {
                "id": poi.get("id"),
                "name_zh": self._clean(poi.get("name")),
                "name_en": None,
                "city_zh": self._clean(
                    poi.get("cityname")
                ),
                "district_zh": self._clean(
                    poi.get("adname")
                ),
                "address_zh": self._clean(
                    poi.get("address")
                ),
                "category": category,
                "amap_category": self._clean(
                    poi.get("type")
                ),
                "typecode": poi_type,
                "coordinates": self._coordinates(
                    poi.get("location")
                ),
                "opening_hours": None,
                "ticket_price_cny": None,
                "source": {
                    "provider": "amap",
                    "poi_id": poi.get("id"),
                    "retrieved_at": retrieved_at
                },
                "verification_status": "poi_found"
            }

            results.append(place)

        return results
