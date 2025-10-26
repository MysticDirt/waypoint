# flights_tool.py
from __future__ import annotations
import os
from datetime import date
from typing import Any, Dict, List, Optional, TypedDict
from serpapi import GoogleSearch
from dotenv import load_dotenv

load_dotenv()


class FlightLeg(TypedDict, total=False):
    airline: str
    flight_number: str
    duration: str
    departure_airport: str
    departure_time: str
    arrival_airport: str
    arrival_time: str
    layovers: List[str]


class FlightOption(TypedDict, total=False):
    title: str
    total_price: Optional[str]
    currency: Optional[str]
    out_duration: Optional[str]
    ret_duration: Optional[str]
    booking_links: List[Dict[str, str]]
    legs_out: List[FlightLeg]
    legs_return: List[FlightLeg]


def _require_api_key() -> str:
    key = os.getenv("SERPAPI_API_KEY")
    if not key:
        raise RuntimeError("Set SERPAPI_API_KEY in your environment.")
    return key


def _fmt_date(d: date | str) -> str:
    return d if isinstance(d, str) else d.isoformat()


def _parse_leg(seg: Dict[str, Any]) -> FlightLeg:
    return FlightLeg(
        airline=seg.get("airline"),
        flight_number=seg.get("flight_number"),
        duration=seg.get("duration"),
        departure_airport=seg.get("departure_airport"),
        departure_time=seg.get("departure_time"),
        arrival_airport=seg.get("arrival_airport"),
        arrival_time=seg.get("arrival_time"),
        layovers=[l.get("name") for l in seg.get("layovers", []) if isinstance(l, dict)],
    )


def _extract_options(bucket: Dict[str, Any]) -> List[FlightOption]:
    out: List[FlightOption] = []
    for f in bucket.get("flights", []):
        out.append(FlightOption(
            title=bucket.get("type") or bucket.get("title"),
            total_price=(f.get("price") or {}).get("price"),
            currency=(f.get("price") or {}).get("currency"),
            out_duration=f.get("total_duration"),
            ret_duration=f.get("return_total_duration"),
            booking_links=[
                {
                    "provider": lb.get("provider_name") or lb.get("type") or "Unknown",
                    "link": lb.get("link"),
                    "price": (lb.get("price") or {}).get("price"),
                }
                for lb in f.get("booking_links", [])
            ],
            legs_out=[_parse_leg(s) for s in f.get("segments", [])],
            legs_return=[_parse_leg(s) for s in f.get("return_segments", [])],
        ))
    return out


def find_flights(
    origin: str,
    destination: str,
    depart_date: date | str,
    return_date: Optional[date | str] = None,
    *,
    currency: str = "USD",
    seats: int = 1,
    cabin: Optional[str] = None,     # ECONOMY | PREMIUM_ECONOMY | BUSINESS | FIRST
    non_stop: Optional[bool] = None, # True => nonstop filter
    hl: str = "en",
    gl: str = "us",
) -> Dict[str, Any]:
    """Calls SerpApi Google Flights and returns normalized flight buckets."""
    _require_api_key()  # ensures key present

    params: Dict[str, Any] = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": _fmt_date(depart_date),
        "currency": currency,
        "seats": str(seats),
        "hl": hl,
        "gl": gl,
        "api_key": os.environ["SERPAPI_API_KEY"],
    }
    if return_date:
        params["return_date"] = _fmt_date(return_date)
    if cabin:
        params["travel_class"] = cabin
    if non_stop is True:
        params["stops"] = 0

    results = GoogleSearch(params).get_dict()

    best_bucket = {"type": "Best departing flights", "flights": results.get("best_flights", [])}
    other_bucket = {"type": "Other departing flights", "flights": results.get("other_flights", [])}
    best_return_bucket = {"type": "Best returning flights", "flights": results.get("best_return_flights", [])}
    other_return_bucket = {"type": "Other returning flights", "flights": results.get("other_return_flights", [])}

    return {
        "best": _extract_options(best_bucket),
        "other": _extract_options(other_bucket),
        "best_return": _extract_options(best_return_bucket),
        "other_return": _extract_options(other_return_bucket),
        "raw": results,
    }
