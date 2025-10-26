# flights_tool.py (hardened)

from __future__ import annotations
import os, json
from datetime import date
from typing import Any, Dict, List, Optional, TypedDict
from serpapi import GoogleSearch

DEBUG = os.getenv("DEBUG_FLIGHTS") == "1"

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

def _safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []

def _safe_dicts(seq: Any) -> List[Dict[str, Any]]:
    return [it for it in _safe_list(seq) if isinstance(it, dict)]

def _parse_leg(seg: Dict[str, Any]) -> FlightLeg:
    return FlightLeg(
        airline=seg.get("airline"),
        flight_number=seg.get("flight_number"),
        duration=seg.get("duration"),
        departure_airport=seg.get("departure_airport"),
        departure_time=seg.get("departure_time"),
        arrival_airport=seg.get("arrival_airport"),
        arrival_time=seg.get("arrival_time"),
        layovers=[l.get("name") for l in _safe_dicts(seg.get("layovers"))],
    )

# --- in flights_tool.py ---

def _pick_price(f: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    p = f.get("price")
    if isinstance(p, dict):
        price_val = p.get("price") or p.get("amount") or p.get("display")
        if price_val is not None:
            return (str(price_val), p.get("currency"))
    if isinstance(p, (int, float)):
        return (str(p), None)
    if isinstance(p, str):
        import re
        m = re.search(r"([$\£\€])?\s*([0-9]+(?:\.[0-9]+)?)", p)
        if m:
            cur = {"$":"USD","£":"GBP","€":"EUR"}.get(m.group(1))
            return (m.group(2), cur)
    return (None, None)

def _parse_leg_variant(seg: Dict[str, Any]) -> FlightLeg:
    # Airline can appear as 'airline', or in 'carrier' obj, or in 'operating_carrier'
    airline_name = (
        seg.get("airline")
        or (seg.get("carrier") or {}).get("name")
        or (seg.get("carrier") or {}).get("airline")
        or (seg.get("operating_carrier") or {}).get("name")
    )
    # Carrier/IATA codes:
    airline_code = (
        (seg.get("carrier") or {}).get("iata")
        or (seg.get("operating_carrier") or {}).get("iata")
        or (seg.get("carrier") or {}).get("code")
        or None
    )

    # Flight number may be:
    #  - 'flight_number'
    #  - 'number'
    #  - nested 'flight' { number / code }
    fno = (
        seg.get("flight_number")
        or seg.get("number")
        or (seg.get("flight") or {}).get("number")
        or (seg.get("flight") or {}).get("code")
    )
    # Compose like "UA123" if we have an airline code + numeric number
    flight_number = None
    if fno:
        fno_str = str(fno)
        if airline_code and not fno_str.upper().startswith(airline_code):
            flight_number = f"{airline_code}{fno_str}"
        else:
            flight_number = fno_str

    dep_air = seg.get("departure_airport") or seg.get("from") or seg.get("departure") or {}
    arr_air = seg.get("arrival_airport")   or seg.get("to")   or seg.get("arrival")   or {}

    def _code_or_name(x):
        if isinstance(x, dict):
            return x.get("code") or x.get("iata") or x.get("name")
        return x

    def _coerce_time(val: Any) -> Optional[str]:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            from datetime import datetime
            try:
                return datetime.utcfromtimestamp(val).strftime("%Y-%m-%dT%H:%M:%S")
            except Exception:
                return None
        return str(val)

    dep_time = _coerce_time(seg.get("departure_time") or seg.get("departure") or (dep_air.get("time") if isinstance(dep_air, dict) else None))
    arr_time = _coerce_time(seg.get("arrival_time")   or seg.get("arrival")   or (arr_air.get("time") if isinstance(arr_air, dict) else None))

    duration = seg.get("duration")
    if isinstance(duration, (int, float)):
        duration = str(int(duration))

    layovers = []
    for l in seg.get("layovers") or []:
        if isinstance(l, dict):
            layovers.append(l.get("name") or l.get("code"))

    return FlightLeg(
        airline=airline_name or airline_code,   # always fill at least something
        flight_number=flight_number,
        duration=duration,
        departure_airport=_code_or_name(dep_air),
        departure_time=dep_time,
        arrival_airport=_code_or_name(arr_air),
        arrival_time=arr_time,
        layovers=layovers,
    )



def _extract_options(bucket: Dict[str, Any]) -> List[FlightOption]:
    out: List[FlightOption] = []
    flights = _safe_list(bucket.get("flights"))
    if not flights and isinstance(bucket.get("flights"), dict):
        flights = _safe_list(bucket["flights"].get("flights"))

    for f in flights:
        if not isinstance(f, dict):
            continue

        # Price (robust)
        total_price, currency = _pick_price(f)

        # Booking links
        links: List[Dict[str, str]] = []
        for lb in _safe_dicts(f.get("booking_links")):
            price_str = None
            if isinstance(lb.get("price"), dict):
                price_str = lb["price"].get("price") or lb["price"].get("amount")
            elif isinstance(lb.get("price"), (int, float, str)):
                price_str = str(lb.get("price"))
            links.append({
                "provider": lb.get("provider_name") or lb.get("type") or "Unknown",
                "link": lb.get("link"),
                "price": price_str,
            })

        # Find leg arrays under several possible keys
        legs_candidates = []
        for key in ("segments", "legs", "flight_legs"):
            if isinstance(f.get(key), list):
                legs_candidates = f[key]
                break
        if not legs_candidates:
            # sometimes nested under 'itinerary': {'outbound': [...], 'return': [...]}
            itin = f.get("itinerary") or {}
            if isinstance(itin, dict):
                legs_candidates = _safe_list(itin.get("outbound"))  # we'll treat outbound here

        legs_out = [_parse_leg_variant(s) for s in _safe_dicts(legs_candidates)]

        # Return legs (if present in familiar keys)
        ret_candidates = []
        for key in ("return_segments", "return_legs"):
            if isinstance(f.get(key), list):
                ret_candidates = f[key]
                break
        if not ret_candidates and isinstance(f.get("itinerary"), dict):
            ret_candidates = _safe_list(f["itinerary"].get("return"))

        legs_return = [_parse_leg_variant(s) for s in _safe_dicts(ret_candidates)]

        # Durations can be ints (minutes) or strings
        out_dur = f.get("total_duration") or f.get("outbound_duration") or f.get("duration")
        ret_dur = f.get("return_total_duration") or f.get("inbound_duration")

        out.append(FlightOption(
            title=bucket.get("type") or bucket.get("title"),
            total_price=total_price,
            currency=currency,
            out_duration=str(out_dur) if out_dur is not None else None,
            ret_duration=str(ret_dur) if ret_dur is not None else None,
            booking_links=links,
            legs_out=legs_out,
            legs_return=legs_return,
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
    """Calls SerpApi Google Flights and returns normalized flight buckets (defensive)."""
    _require_api_key()

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

    raw = GoogleSearch(params).get_dict()

    # If something upstream gave us a JSON string, parse it
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}

    # Normalize buckets: allow weird shapes and ensure we pass a list into _extract_options
    def bucketize(title: str, items: Any) -> Dict[str, Any]:
        # items can be list/dict/None/int/etc. Normalize to list under key "flights"
        if isinstance(items, list):
            flights = items
        elif isinstance(items, dict) and isinstance(items.get("flights"), list):
            flights = items["flights"]
        else:
            flights = []  # fallback
            if DEBUG and items is not None:
                print(f"[find_flights] Unexpected bucket type for '{title}':", type(items), items)
        return {"type": title, "flights": flights}

    best_bucket         = bucketize("Best departing flights", raw.get("best_flights"))
    other_bucket        = bucketize("Other departing flights", raw.get("other_flights"))
    best_return_bucket  = bucketize("Best returning flights", raw.get("best_return_flights"))
    other_return_bucket = bucketize("Other returning flights", raw.get("other_return_flights"))

    normalized = {
        "best": _extract_options(best_bucket),
        "other": _extract_options(other_bucket),
        "best_return": _extract_options(best_return_bucket),
        "other_return": _extract_options(other_return_bucket),
        "raw": raw,  # keep for debugging/inspection
    }

    # Final guard: ensure lists
    for k in ("best", "other", "best_return", "other_return"):
        if not isinstance(normalized.get(k), list):
            normalized[k] = []
    return normalized
