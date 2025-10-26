# proactive_life_manager_agent.py
# uAgents-only server: planning (Claude), refinement (Groq), and profile context
# Tools: SerpApi (Google Flights / Hotels / Events) via `google-search-results` client
#
# Setup:
#   pip install uagents anthropic groq google-search-results python-dotenv
#   export ANTHROPIC_API_KEY=...
#   export GROQ_API_KEY=...
#   export SERPAPI_API_KEY=...
#
# Run:
#   python proactive_life_manager_agent.py
#
# Notes:
# - This file intentionally uses uAgents for REST endpoints (no FastAPI).
# - Stage 1 planning is forced to emit a JSON array by prefilling '['.
# - Stage 2 synthesis is forced to emit a JSON object by prefilling '{'.
# - Server-side conflict resolution removes overlaps; IDs are ensured.
# - Tools normalize prices, times, coordinates; events include end times when possible.

import os
import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import anthropic
from groq import Groq
from serpapi import GoogleSearch
from dotenv import load_dotenv
from uagents import Agent, Context, Model

# ---- External wrapper (your existing normalized SerpApi Google Flights wrapper) ----
# Ensure you have flights_tool.py in the same directory with a `find_flights(...)` function as discussed.
from flights_tool import find_flights

# =========================
# 1) ENV & CLIENTS
# =========================

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in environment")
if not SERPAPI_API_KEY:
    raise ValueError("SERPAPI_API_KEY not found in environment")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in environment")

claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

# =========================
# 2) DATA MODELS
# =========================

class PlanRequest(Model):
    prompt: str  # e.g., "Plan a cheap cultural weekend in Chicago"
    conversation_history: list = []  # List of previous messages
    itinerary: list = []  # Existing itinerary items
    locations: list = []  # Existing locations

class AgentPlanResponse(Model):
    status: str           # "success" | "needs_clarification" | "error"
    itinerary: list       # List[dict] of itinerary items
    logs: list            # List[str] for trace / notes
    locations: list       # List[dict] map markers
    options: list = []    # List[dict] of selectable options (flights, events, hotels)

class RefineRequest(Model):
    itinerary: list
    locations: list

class UserProfile(Model):
    city: str
    latitude: float
    longitude: float
    timezone: str

# Defaults for profile/context
USER_CITY = os.getenv("USER_CITY", "Berkeley, CA, USA")
USER_LAT = float(os.getenv("USER_LAT", "37.8715"))
USER_LON = float(os.getenv("USER_LON", "-122.2730"))
USER_TIMEZONE = os.getenv("USER_TIMEZONE", "America/Los_Angeles")

# ------- Default home-airport inference from profile city -------
def infer_home_airport(city_text: str) -> str | None:
    """
    Best-effort mapping from a user's city text to a sensible default IATA.
    Extend this table as needed. Fallback is None (we'll ask the user).
    """
    if not city_text:
        return None
    c = city_text.lower()

    # Bay Area
    if "berkeley" in c or "oakland" in c: return "OAK"
    if "san francisco" in c: return "SFO"
    if "san jose" in c: return "SJC"

    # Big metros
    if "seattle" in c: return "SEA"
    if "los angeles" in c: return "LAX"
    if "new york" in c or "nyc" in c or "manhattan" in c or "brooklyn" in c: return "JFK"
    if "boston" in c: return "BOS"
    if "chicago" in c: return "ORD"
    if "washington" in c and ("dc" in c or "d.c." in c): return "DCA"
    if "dallas" in c: return "DFW"
    if "atlanta" in c: return "ATL"
    if "miami" in c: return "MIA"
    if "denver" in c: return "DEN"
    if "phoenix" in c: return "PHX"
    if "houston" in c: return "IAH"
    if "austin" in c: return "AUS"
    if "las vegas" in c: return "LAS"
    if "san diego" in c: return "SAN"
    if "portland" in c and "or" in c: return "PDX"

    # Generic: nothing matched
    return None


current_profile = UserProfile(
    city=USER_CITY,
    latitude=USER_LAT,
    longitude=USER_LON,
    timezone=USER_TIMEZONE,
)

# =========================
# 3) REAL TOOLS (SerpApi)
# =========================

def search_real_hotels(query: str) -> str:
    """
    Searches SerpApi Google Hotels and returns normalized hotel cards with price_per_night.
    Returns JSON string: {"hotels":[{...},{...}]}
    """
    print(f"TOOL: Searching hotels for '{query}'")
    try:
        from datetime import date, timedelta
        today = date.today()
        tomorrow = today + timedelta(days=1)

        params = {
            "engine": "google_hotels",
            "q": query,
            "api_key": SERPAPI_API_KEY,
            "check_in_date": today.strftime("%Y-%m-%d"),
            "check_out_date": tomorrow.strftime("%Y-%m-%d"),
            "currency": "USD",
            "hl": "en",
            "gl": "us",
        }
        results = GoogleSearch(params).get_dict()
        props = results.get("properties", [])[:8]

        def norm(p: Dict[str, Any]) -> Dict[str, Any]:
            price_info = p.get("rate_per_night") or p.get("price") or {}
            extracted = (
                price_info.get("extracted_lowest")
                or price_info.get("extracted_price")
                or p.get("extracted_price")
            )
            currency = price_info.get("currency") or p.get("currency") or "USD"
            price_text = (
                price_info.get("lowest")
                or price_info.get("display")
                or p.get("price_qualifier")
                or p.get("price")
                or (f"{extracted} {currency}" if extracted else None)
            )
            coords = p.get("gps_coordinates") or {}
            link = p.get("link") or p.get("all_options_link") or p.get("booking_link")

            return {
                "name": p.get("name"),
                "description": p.get("description"),
                "price_per_night": extracted,   # numeric if available
                "price_text": price_text,       # fallback for UI
                "currency": currency,
                "rating": p.get("overall_rating") or p.get("rating"),
                "reviews": p.get("reviews"),
                "amenities": p.get("amenities"),
                "link": link,
                "latitude": coords.get("latitude"),
                "longitude": coords.get("longitude"),
                "address": p.get("address"),
                "neighborhood": p.get("neighborhood"),
            }

        hotels = [norm(p) for p in props]
        hotels = [h for h in hotels if h["name"]][:5]

        if not hotels:
            return json.dumps({
                "error": "No hotels found for that query",
                "user_prompt_needed": True,
                "suggested_questions": [
                    "What’s your nightly budget cap (USD)?",
                    "Do you want downtown or near the airport?",
                    "Do you prefer 3★, 4★, or 5★?"
                ]
            })

        return json.dumps({"hotels": hotels})

    except Exception as e:
        print(f"Error in search_real_hotels: {e}")
        return json.dumps({"error": str(e)})

# --- in your main agent file, replace search_real_events with:

def search_real_events(query: str) -> str:
    """
    Robust SerpApi events lookup with fallbacks:
      A) google_events with location + ISO 'YYYY-MM-DD to YYYY-MM-DD' (when clean)
      B) google_events with location only (dates pushed into q implicitly)
      C) google web search fallback (Eventbrite/Ticketmaster/StubHub) normalized

    Returns JSON string:
      {"events": [ {title, description, start_date, end_date, start_time, end_time,
                    venue:{name,address,latitude,longitude}, price, price_text, currency, link, source} ... ]}
    or a clarifier:
      {"error": "...", "user_prompt_needed": true, "suggested_questions": [...]}
    """
    print(f"TOOL: Searching events for '{query}'")
    try:
        import re
        from datetime import datetime as _dt, timedelta
        from serpapi import GoogleSearch

        # --- 0) Target city: prefer one mentioned in query; else user's city ---
        CITY_CANON = {
            "los angeles": "Los Angeles, CA", "san francisco": "San Francisco, CA",
            "new york": "New York, NY", "seattle": "Seattle, WA", "boston": "Boston, MA",
            "chicago": "Chicago, IL", "austin": "Austin, TX", "denver": "Denver, CO",
            "miami": "Miami, FL", "las vegas": "Las Vegas, NV", "san diego": "San Diego, CA",
            "portland": "Portland, OR", "phoenix": "Phoenix, AZ", "dallas": "Dallas, TX",
            "houston": "Houston, TX", "atlanta": "Atlanta, GA", "washington": "Washington, DC",
            "san jose": "San Jose, CA",
        }
        qlow = query.lower()
        target_city = None
        for k, canon in CITY_CANON.items():
            if k in qlow:
                target_city = canon
                break
        if not target_city:
            base = (current_profile.city or "United States").split(",")
            target_city = base[0].strip()
            if len(base) > 1:
                target_city = f"{base[0].strip()}, {base[1].strip()}"

        # --- 1) Build date range as 'YYYY-MM-DD to YYYY-MM-DD' when clean ---
        m_iso = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:\.\.|-|–|to)\s*(\d{4}-\d{2}-\d{2})", query)
        date_range = None
        if m_iso:
            date_range = f"{m_iso.group(1)} to {m_iso.group(2)}"
        else:
            # Parse "Nov 21-23" / "November 21-23"
            m_md = re.search(r"\b([A-Za-z]{3,9})\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\b", query)
            if m_md:
                mon, d1, d2 = m_md.group(1), int(m_md.group(2)), int(m_md.group(3))
                year = _dt.utcnow().year
                try:
                    start = _dt.strptime(f"{mon} {d1} {year}", "%b %d %Y")
                except ValueError:
                    start = _dt.strptime(f"{mon} {d1} {year}", "%B %d %Y")
                if start < _dt.utcnow() - timedelta(days=30):
                    year += 1
                    try:
                        start = _dt.strptime(f"{mon} {d1} {year}", "%b %d %Y")
                    except ValueError:
                        start = _dt.strptime(f"{mon} {d1} {year}", "%B %d %Y")
                end = start.replace(day=d2)
                date_range = f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"

        # --- helpers ---
        def add_year_if_missing(md: str | None) -> str | None:
            if not md:
                return None
            if re.match(r"^\d{4}-\d{2}-\d{2}$", md):
                return md
            try:
                dt = _dt.strptime(md + f" {_dt.utcnow().year}", "%b %d %Y")
            except Exception:
                try:
                    dt = _dt.strptime(md + f" {_dt.utcnow().year}", "%B %d %Y")
                except Exception:
                    return None
            if dt < _dt.utcnow() - timedelta(days=30):
                dt = dt.replace(year=dt.year + 1)
            return dt.strftime("%Y-%m-%d")

        def parse_times(e):
            d = e.get("date", {}) or {}
            start_date = add_year_if_missing(d.get("start_date"))
            end_date = add_year_if_missing(d.get("end_date") or d.get("start_date"))
            start_time = d.get("start_time")
            end_time = d.get("end_time")
            when = d.get("when") or ""
            if not end_time and "–" in when:
                mm = re.search(r"–\s*([0-9]{1,2}:[0-9]{2}\s*[AP]M)", when)
                if mm:
                    end_time = mm.group(1)
            return start_date, end_date, start_time, end_time

        def parse_price(e):
            tix = e.get("ticket_info") or []
            price_text, extracted, currency, link = None, None, None, None
            for t in tix:
                price_text = price_text or t.get("price")
                link = link or t.get("link")
            if price_text:
                mm = re.search(r"([A-Z]{3}|\$|€|£)?\s*([0-9]+(?:\.[0-9]+)?)", price_text)
                if mm:
                    symbol_or_ccy, num = mm.group(1), mm.group(2)
                    extracted = float(num)
                    currency = {"$":"USD","€":"EUR","£":"GBP"}.get(symbol_or_ccy, symbol_or_ccy or "USD")
            return extracted, currency, price_text, link

        def normalize(events_raw):
            out = []
            for ev in (events_raw or []):
                if not isinstance(ev, dict):
                    continue
                # loosen city filtering: trust SerpApi's location bias
                sd, ed, st, et = parse_times(ev)
                ex_price, ccy, price_text, ticket_link = parse_price(ev)
                venue = ev.get("venue") if isinstance(ev.get("venue"), dict) else {}
                coords = (venue or {}).get("gps_coordinates") or {}
                out.append({
                    "title": ev.get("title"),
                    "description": ev.get("description"),
                    "start_date": sd, "end_date": ed,
                    "start_time": st, "end_time": et,
                    "venue": {
                        "name": venue.get("name"),
                        "address": venue.get("address"),
                        "latitude": coords.get("latitude"),
                        "longitude": coords.get("longitude"),
                    },
                    "price": ex_price, "price_text": price_text,
                    "currency": ccy or "USD",
                    "link": ticket_link or ev.get("link"),
                    "source": ev.get("source") or "google_events",
                })
            # keep only items with a title + some date
            out = [n for n in out if n["title"] and n["start_date"]]
            
            # Filter based on trip dates if available
            global _trip_dates
            if _trip_dates.get("start_date") and _trip_dates.get("end_date"):
                try:
                    trip_start = _dt.strptime(_trip_dates["start_date"], "%Y-%m-%d")
                    trip_end = _dt.strptime(_trip_dates["end_date"], "%Y-%m-%d")
                    # Allow events up to 7 days after trip end
                    trip_end_extended = trip_end + timedelta(days=7)
                    
                    filtered = []
                    for event in out:
                        if event["start_date"]:
                            try:
                                event_date = _dt.strptime(event["start_date"], "%Y-%m-%d")
                                # Keep event if it's within [trip_start, trip_end + 7 days]
                                if trip_start <= event_date <= trip_end_extended:
                                    filtered.append(event)
                            except Exception:
                                # If date parsing fails, keep the event
                                filtered.append(event)
                    out = filtered
                    print(f"Filtered events based on trip dates {_trip_dates['start_date']} to {_trip_dates['end_date']} (+7 days): {len(out)} events remain")
                except Exception as e:
                    print(f"Error filtering events by trip dates: {e}")
            
            return out

        # --- A) strict google_events (only if we have a clean ISO range) ---
        base = {"engine": "google_events", "api_key": SERPAPI_API_KEY, "hl": "en", "gl": "us"}
        strict = dict(base, q=query, location=target_city)
        if date_range:
            strict["date"] = date_range  # only add when clean

        res = GoogleSearch(strict).get_dict()
        events = normalize(res.get("events_results"))

        # --- B) relaxed google_events (no explicit date; keep location; dates remain in q implicitly) ---
        if not events:
            relaxed = dict(base, q=query, location=target_city)
            relaxed.pop("date", None)
            res2 = GoogleSearch(relaxed).get_dict()
            events = normalize(res2.get("events_results"))

        # --- C) web fallback: ticketing sites ---
        if not events:
            date_for_q = ""
            if date_range:
                try:
                    s, e = date_range.split(" to ")
                    sd = _dt.strptime(s, "%Y-%m-%d").strftime("%b %d, %Y")
                    ed = _dt.strptime(e, "%Y-%m-%d").strftime("%b %d, %Y")
                    date_for_q = f" {sd} to {ed}"
                except Exception:
                    date_for_q = f" {date_range}"
            web_q = f'{target_city} events{date_for_q} site:eventbrite.com OR site:ticketmaster.com OR site:stubhub.com'
            web = {"engine": "google", "api_key": SERPAPI_API_KEY, "q": web_q, "hl": "en", "gl": "us", "num": "10"}
            gres = GoogleSearch(web).get_dict()
            organic = gres.get("organic_results", []) or []
            norm2 = []
            for r in organic:
                if not isinstance(r, dict): 
                    continue
                title = r.get("title")
                link = r.get("link")
                snippet = r.get("snippet")
                if title and link:
                    norm2.append({
                        "title": title,
                        "description": snippet,
                        "start_date": None, "end_date": None,
                        "start_time": None, "end_time": None,
                        "venue": {"name": None, "address": None, "latitude": None, "longitude": None},
                        "price": None, "price_text": None, "currency": "USD",
                        "link": link, "source": "web",
                    })
            events = norm2

        events = events[:12]
        if not events:
            return json.dumps({
                "error": f"No events found near {target_city}",
                "user_prompt_needed": True,
                "suggested_questions": [
                    f"Broaden beyond {target_city} or include nearby neighborhoods?",
                    "Any specific event types (concerts, comedy, sports, museums)?",
                    "Extend the date window by ±1 day?"
                ]
            })

        return json.dumps({"events": events})

    except Exception as e:
        print(f"Error in search_real_events: {e}")
        return json.dumps({"error": str(e), "user_prompt_needed": True})


def search_real_flights(query: str) -> str:
    """
    Robust Google Flights normalizer for whatever find_flights(...) returns:
      - list
      - {"best":[...], "other":[...], ...}
      - {"results": {"best":[...], ...}}
      - raw SerpApi: {"best_flights":[...], "other_flights":[...]}
    Always returns:
      {
        "query_parsed": {...},
        "results": {"best":[...], "other":[...], "best_return":[...], "other_return":[...]}
      }
    """
    print("search_real_flights v3.1")
    print(f"TOOL: Searching flights for '{query}'")
    try:
        import re, json as _json, os

        # ---------- Parse query ----------
        od_match = re.search(r"\b([A-Za-z]{3,}?)\b\s*(?:to|->|—|-)\s*\b([A-Za-z]{3,}?)\b", query, flags=re.IGNORECASE)
        origin = od_match.group(1).upper() if od_match else None
        destination = od_match.group(2).upper() if od_match else None

        dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", query)
        depart_date = dates[0] if len(dates) >= 1 else None
        return_date = dates[1] if len(dates) >= 2 else None

        non_stop = bool(re.search(r"\bnon[-\s]?stop\b", query, flags=re.IGNORECASE))

        if not origin:
            origin = infer_home_airport(current_profile.city)

        cabin_map = {
            "economy": "ECONOMY",
            "premium economy": "PREMIUM_ECONOMY",
            "business": "BUSINESS",
            "first": "FIRST",
        }
        cabin = None
        for k, v in cabin_map.items():
            if re.search(rf"\b{k}\b", query, flags=re.IGNORECASE):
                cabin = v
                break

        seats = 1
        m_seats = re.search(r"\b(\d+)\s*(?:seats?|adults?)\b", query, flags=re.IGNORECASE)
        if m_seats:
            seats = max(1, int(m_seats.group(1)))

        currency = "USD"
        m_ccy = re.search(r"\b(USD|EUR|GBP|CAD|AUD|JPY|INR|CNY|KRW|MXN)\b", query, flags=re.IGNORECASE)
        if m_ccy:
            currency = m_ccy.group(1).upper()

        if not origin or not destination or not depart_date:
            hints = [
                "What cities or airports are you flying between?",
                "What is your departure date in YYYY-MM-DD?",
                "Do you need a return date?"
            ]
            if not origin and current_profile.city:
                hints.insert(0, f"What's your preferred airport near {current_profile.city}?")
            return _json.dumps({
                "error": "Missing origin/destination/depart_date",
                "user_prompt_needed": True,
                "suggested_questions": hints
            })

        # ---------- Call wrapper ----------
        data = find_flights(
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            return_date=return_date,
            currency=currency,
            seats=seats,
            cabin=cabin,
            non_stop=non_stop,
        )

        # ---------- Defensive coercions ----------
        # parse if JSON string
        if isinstance(data, str):
            try:
                data = _json.loads(data)
            except Exception:
                data = []  # treat as empty

        if os.environ.get("DEBUG_FLIGHTS") == "1":
            print("[find_flights type]:", type(data).__name__)
            if isinstance(data, dict):
                print("[find_flights dict keys]:", list(data.keys())[:20])
            elif isinstance(data, list) and data:
                print("[find_flights list[0] type]:", type(data[0]).__name__)

        # ---------- helpers ----------
        def _lod(x):
            return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []

        def _coerce_results(x):
            """
            Return dict with keys: best, other, best_return, other_return (lists of dicts).
            Never calls .get on a list.
            """
            best = []; other = []; best_ret = []; other_ret = []

            if isinstance(x, list):
                best = _lod(x)

            elif isinstance(x, dict):
                r = x.get("results")
                if isinstance(r, dict):
                    best      = _lod(r.get("best", []))
                    other     = _lod(r.get("other", []))
                    best_ret  = _lod(r.get("best_return", []))
                    other_ret = _lod(r.get("other_return", []))
                else:
                    best      = _lod(x.get("best", []))
                    other     = _lod(x.get("other", []))
                    best_ret  = _lod(x.get("best_return", []))
                    other_ret = _lod(x.get("other_return", []))
                    if not any([best, other, best_ret, other_ret]):
                        # raw SerpApi fallback
                        best      = _lod(x.get("best_flights", []))
                        other     = _lod(x.get("other_flights", []))
                        best_ret  = _lod(x.get("best_return_flights", []))
                        other_ret = _lod(x.get("other_return_flights", []))

            return {
                "best": best, "other": other,
                "best_return": best_ret, "other_return": other_ret
            }

        def _parse_serpapi_legs(item):
            if not isinstance(item, dict):
                return []
            legs = []
            for seg in _lod(item.get("flights") or []):  # <-- your logs show 'flights'
                dep = seg.get("departure_airport") or seg.get("from") or seg.get("departure") or {}
                arr = seg.get("arrival_airport")   or seg.get("to")   or seg.get("arrival")   or {}

                airline_name = (
                    seg.get("airline") or
                    (seg.get("carrier") or {}).get("name") or
                    (seg.get("operating_carrier") or {}).get("name")
                )
                airline_code = (
                    (seg.get("carrier") or {}).get("iata") or
                    (seg.get("carrier") or {}).get("code") or
                    (seg.get("operating_carrier") or {}).get("iata")
                )
                fno = seg.get("flight_number") or seg.get("number") or (seg.get("flight") or {}).get("number") or (seg.get("flight") or {}).get("code")
                if fno:
                    fno_str = str(fno)
                    flight_number = f"{airline_code}{fno_str}" if (airline_code and not fno_str.upper().startswith(airline_code)) else fno_str
                else:
                    flight_number = None

                def _code_or_name(xv):
                    if isinstance(xv, dict):
                        return xv.get("code") or xv.get("iata") or xv.get("name")
                    return xv

                dep_time = seg.get("departure_time") or (dep.get("time") if isinstance(dep, dict) else None)
                arr_time = seg.get("arrival_time")   or (arr.get("time") if isinstance(arr, dict) else None)

                duration = seg.get("duration")
                if isinstance(duration, (int, float)):
                    duration = str(int(duration))

                layovers = []
                for s in (seg.get("stops") or seg.get("layovers") or []):
                    if isinstance(s, dict):
                        layovers.append(s.get("name") or s.get("code"))
                    else:
                        layovers.append(str(s))

                legs.append({
                    "airline": airline_name or airline_code,
                    "flight_number": flight_number,
                    "departure_airport": _code_or_name(dep),
                    "departure_time": str(dep_time) if dep_time else None,
                    "arrival_airport": _code_or_name(arr),
                    "arrival_time": str(arr_time) if arr_time else None,
                    "duration": duration,
                    "layovers": layovers,
                })
            return legs

        def _shrink_item(f):
            if not isinstance(f, dict):
                return None

            # price
            price, ccy = None, None
            p = f.get("price") or f.get("total_price")
            if isinstance(p, dict):
                price = str(p.get("price") or p.get("amount") or p.get("display") or "").strip() or None
                ccy = p.get("currency")
            elif isinstance(p, (int, float, str)):
                price = str(p)

            # durations
            out_dur = f.get("out_duration") or f.get("total_duration")
            ret_dur = f.get("ret_duration") or f.get("return_total_duration")
            if isinstance(out_dur, (int, float)): out_dur = str(int(out_dur))
            if isinstance(ret_dur, (int, float)): ret_dur = str(int(ret_dur))

            # legs: prefer normalized legs_out; else parse SerpApi 'flights'
            legs_out = _lod(f.get("legs_out") or [])
            if not legs_out and isinstance(f.get("flights"), list):
                legs_out = _parse_serpapi_legs(f)

            # booking links
            links = []
            for bl in _lod(f.get("booking_links") or []):
                links.append({
                    "provider": bl.get("provider_name") or bl.get("provider") or bl.get("type"),
                    "link": bl.get("link"),
                    "price": str(bl.get("price")) if bl.get("price") is not None else None,
                })

            return {
                "title": f.get("title") or f.get("type") or "Departing flight",
                "total_price": price,
                "currency": ccy or currency,
                "out_duration": out_dur,
                "ret_duration": ret_dur,
                "legs_out": legs_out,
                "booking_links": links[:2],
            }

        norm = _coerce_results(data)

        # shrink to top 3 per bucket
        def shrink(bucket):
            out = []
            for f in bucket[:3]:
                item = _shrink_item(f)
                if item:
                    out.append(item)
            return out

        results_obj = {
            "best": shrink(norm["best"]),
            "other": shrink(norm["other"]),
            "best_return": shrink(norm["best_return"]),
            "other_return": shrink(norm["other_return"]),
        }

        if os.environ.get("DEBUG_FLIGHTS") == "1":
            print("[normalized counts]:", {k: len(v) for k, v in results_obj.items()})
            if norm["best"]:
                print("[sample best keys]:", list(norm["best"][0].keys()))

        if not any(results_obj.values()):
            return _json.dumps({
                "error": "No flights found for the given parameters",
                "user_prompt_needed": True,
                "suggested_questions": [
                    "Are you open to connections or different times?",
                    "What’s your max budget for flights?",
                    "Should I expand the date window by ±1 day?"
                ],
                "query_parsed": {
                    "origin": origin,
                    "destination": destination,
                    "depart_date": depart_date,
                    "return_date": return_date,
                    "non_stop": non_stop,
                    "cabin": cabin,
                    "seats": seats,
                    "currency": currency,
                }
            })

        return _json.dumps({
            "query_parsed": {
                "origin": origin,
                "destination": destination,
                "depart_date": depart_date,
                "return_date": return_date,
                "non_stop": non_stop,
                "cabin": cabin,
                "seats": seats,
                "currency": currency,
            },
            "results": results_obj
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error in search_real_flights: {e}")
        return json.dumps({"error": str(e), "user_prompt_needed": True})




AVAILABLE_TOOLS = {
    "search_hotels": search_real_hotels,
    "search_events": search_real_events,
    "search_flights": search_real_flights,
}

# =========================
# 4) HELPERS (server-side safety)
# =========================

ISO_FMT = "%Y-%m-%dT%H:%M:%S"

def _parse_iso(s: Optional[str]):
    if not s:
        return None
    try:
        s2 = s.replace(" ", "T")
        if len(s2) == 16:  # "YYYY-MM-DDTHH:MM"
            s2 += ":00"
        return datetime.strptime(s2, ISO_FMT)
    except Exception:
        return None

def _conflicts(a: Dict[str, Any], b: Dict[str, Any], buffer_minutes=30) -> bool:
    sa, ea = _parse_iso(a.get("startTime")), _parse_iso(a.get("endTime"))
    sb, eb = _parse_iso(b.get("startTime")), _parse_iso(b.get("endTime"))
    if not sa or not sb:
        return False
    if not ea: ea = sa + timedelta(minutes=90)
    if not eb: eb = sb + timedelta(minutes=90)
    # Apply buffer
    ea = ea + timedelta(minutes=buffer_minutes)
    sb = sb - timedelta(minutes=buffer_minutes)
    return sa < eb and sb < ea

def enforce_no_overlaps(plan: Dict[str, Any]) -> Dict[str, Any]:
    items = plan.get("itinerary", [])
    logs = plan.get("logs", [])
    if not isinstance(logs, list):
        logs = []
        plan["logs"] = logs

    def keyfn(x: Dict[str, Any]):
        t = _parse_iso(x.get("startTime"))
        return t or datetime.max

    items.sort(key=keyfn)
    kept, removed = [], []
    for item in items:
        if any(_conflicts(item, k, buffer_minutes=30) for k in kept):
            removed.append(item)
        else:
            kept.append(item)
    if removed:
        plan["itinerary"] = kept
        for r in removed:
            logs.append(f"conflict_removed: '{r.get('title')}' at {r.get('startTime')}")
    return plan

def ensure_ids(plan: Dict[str, Any]) -> Dict[str, Any]:
    for item in plan.get("itinerary", []):
        if not item.get("id"):
            item["id"] = str(uuid.uuid4())
    return plan

def safe_json_from_prefill_array(text: str) -> List[Dict[str, Any]]:
    s = "[" + text
    # crude guard if no closing bracket
    if "]" not in s:
        s += "]"
    s = s.split("]")[0] + "]"
    return json.loads(s)

def safe_json_from_prefill_object(text: str) -> Dict[str, Any]:
    s = "{" + text
    # strip accidental fences if any
    if "```json" in s:
        s = s.split("```json\n")[1].split("```")[0]
    elif "```" in s:
        s = s.split("```")[1].split("```")[0]
    return json.loads(s)

# Global variable to store trip dates for event filtering
_trip_dates = {"start_date": None, "end_date": None}

def extract_trip_context(conversation_history: List[Dict[str, Any]], current_itinerary: List[Dict[str, Any]]) -> str:
    """
    Extract key trip details from conversation history and current itinerary to maintain context.
    Returns a formatted string with trip context that can be prepended to prompts.
    Also updates global _trip_dates for event filtering.
    """
    global _trip_dates
    context_parts = []
    
    # Extract from itinerary if available
    if current_itinerary:
        destinations = set()
        dates = []
        for item in current_itinerary:
            # Extract destinations from titles/descriptions
            if item.get('details', {}).get('flight'):
                flight = item['details']['flight']
                if flight.get('arrival_airport'):
                    dest = flight['arrival_airport']
                    if isinstance(dest, dict):
                        destinations.add(dest.get('code', ''))
                    else:
                        destinations.add(str(dest))
            # Extract dates from all items
            if item.get('startTime'):
                try:
                    date_str = item['startTime'].split('T')[0]
                    dates.append(date_str)
                except:
                    pass
        
        if destinations:
            context_parts.append(f"Destination(s): {', '.join(destinations)}")
        if dates:
            sorted_dates = sorted(dates)
            # Store trip dates globally for event filtering
            _trip_dates["start_date"] = sorted_dates[0]
            _trip_dates["end_date"] = sorted_dates[-1] if len(sorted_dates) > 1 else sorted_dates[0]
            
            if len(sorted_dates) >= 2:
                context_parts.append(f"Trip dates: {sorted_dates[0]} to {sorted_dates[-1]}")
            elif sorted_dates:
                context_parts.append(f"Trip date: {sorted_dates[0]}")
    
    # Extract from conversation history - look for explicit date mentions
    if conversation_history and not dates:
        import re
        for msg in conversation_history[-5:]:
            content = msg.get('content', '')
            # Look for ISO date patterns
            date_matches = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', content)
            if date_matches:
                dates.extend(date_matches)
        
        if dates:
            sorted_dates = sorted(set(dates))
            _trip_dates["start_date"] = sorted_dates[0]
            _trip_dates["end_date"] = sorted_dates[-1] if len(sorted_dates) > 1 else sorted_dates[0]
            if len(sorted_dates) >= 2:
                context_parts.append(f"Trip dates: {sorted_dates[0]} to {sorted_dates[-1]}")
            elif sorted_dates:
                context_parts.append(f"Trip date: {sorted_dates[0]}")
    
    if context_parts:
        return "TRIP CONTEXT: " + " | ".join(context_parts) + "\n"
    return ""

def build_conversation_messages(conversation_history: List[Dict[str, Any]], current_prompt: str, context_prefix: str = "") -> List[Dict[str, str]]:
    """
    Build a proper message history for Claude API that includes conversation context.
    Converts frontend conversation format to Claude's expected format.
    """
    messages = []
    
    # Add previous conversation turns
    for msg in conversation_history:
        role = msg.get('role')
        content = msg.get('content', '')
        
        # Skip empty messages or system messages
        if not content or role not in ['user', 'assistant']:
            continue
        
        # Claude expects 'user' and 'assistant' roles
        messages.append({
            "role": role,
            "content": content
        })
    
    # Add current prompt
    messages.append({
        "role": "user",
        "content": context_prefix + current_prompt
    })
    
    return messages

# =========================
# 5) AGENT & ENDPOINTS (uAgents only)
# =========================

agent = Agent(
    name="proactive_life_manager_agent",
    port=8001,
    seed="my_cal_hacks_secret_seed_phrase"
)

@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info("Agent started (uAgents-only). Waiting for planning/refinement requests...")

# ---- PLAN endpoint: Stage 1 & 2 with JSON prefills
@agent.on_rest_post("/plan", PlanRequest, AgentPlanResponse)
async def handle_plan_request(ctx: Context, msg: PlanRequest) -> AgentPlanResponse:
    logs: List[str] = []
    goal = msg.prompt.strip()

    now_iso = datetime.utcnow().isoformat() + "Z"
    context_prefix = (
        f"CONTEXT: user_city={current_profile.city}; user_lat={current_profile.latitude}; "
        f"user_lon={current_profile.longitude}; user_timezone={current_profile.timezone}; "
        f"now_utc={now_iso}. Always plan into the future from now; avoid past dates.\n"
    )
    
    # Extract trip context from conversation history and itinerary
    trip_context = extract_trip_context(msg.conversation_history, msg.itinerary)
    full_context = context_prefix + trip_context

    # ---- Stage 1: Planning (force JSON array)
    plan_system_prompt = f"""
You are a planning AI. Output a JSON array ONLY. No prose, no notes, no markdown.

Rules:
- REMEMBER THE TRIP CONTEXT: If the user has already specified a destination, dates, or preferences in previous messages, USE THEM.
- **CRITICAL: REMEMBER TRIP DATES** - Once trip start and end dates are established, ALWAYS use them for all subsequent searches.
- When searching for events, ALWAYS include the trip dates in the query (e.g., "Chicago events 2025-11-21 to 2025-11-23").
- The system will automatically filter events to show only those between trip start and trip end + 7 days.
- If the user does not specify an ORIGIN airport for flights, use the user's home metro based on profile (e.g., {current_profile.city}) and prefer the primary airport (use our heuristic).
- For events, default search 'location' to the destination city mentioned in the trip context or user's city: {current_profile.city}.
- Never pick dates in the past.
- Flights query MUST include origin, destination, and a future depart date (YYYY-MM-DD).
- If unsure about return, include a best-guess (Fri–Sun).
- Tools you can call: {json.dumps(list(AVAILABLE_TOOLS.keys()))}
- When user asks follow-up questions like "show me more events" or "find cheaper flights", refer to the trip context to know which destination and dates to search.
- MAINTAIN DATE CONSISTENCY: If trip dates are in the trip context, use those exact dates for all event and hotel searches.

Output format:
[
  {{"tool_name": "search_flights", "query": "SFO to SEA depart 2025-11-21 return 2025-11-23"}},
  {{"tool_name": "search_hotels",  "query": "Seattle downtown budget"}},
  {{"tool_name": "search_events",  "query": "Seattle indoor events Nov 21-23"}}
]
"""
    try:
        logs.append("Planning with Claude…")
        
        # Build conversation messages with history
        planning_messages = build_conversation_messages(
            msg.conversation_history,
            goal,
            full_context
        )
        
        # Add the assistant prefill
        planning_messages.append({"role": "assistant", "content": "["})
        
        plan_message = claude_client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=plan_system_prompt,
            messages=planning_messages,
            temperature=0.2,
        )
        tool_plan = safe_json_from_prefill_array(plan_message.content[0].text)
        logs.append(f"Plan steps: {tool_plan}")
    except Exception as e:
        logs.append(f"Error in planning phase: {e}")
        return AgentPlanResponse(status="error", itinerary=[], logs=logs, locations=[])

    # ---- Stage 1b: Execute tool plan
    tool_results: List[Dict[str, Any]] = []
    logs.append("Executing tool plan…")
    for task in tool_plan:
        name = task.get("tool_name")
        q = task.get("query")
        if name in AVAILABLE_TOOLS:
            try:
                result_json = AVAILABLE_TOOLS[name](q)  # returns JSON string
                tool_results.append({"tool": name, "query": q, "result": result_json})
                logs.append(f"OK: {name}('{q}')")
            except Exception as e:
                tool_results.append({"tool": name, "query": q, "result": json.dumps({"error": str(e)})})
                logs.append(f"ERR: {name}('{q}') -> {e}")
        else:
            logs.append(f"Unknown tool requested: {name}")
    
    ctx.logger.info(tool_results)
    
    # Extract any clarification questions from tool results
    clarification_needed = False
    all_questions = []
    for result in tool_results:
        try:
            result_data = json.loads(result.get("result", "{}"))
            if result_data.get("user_prompt_needed"):
                clarification_needed = True
                suggested = result_data.get("suggested_questions", [])
                if suggested:
                    all_questions.extend(suggested)
                error_msg = result_data.get("error", "")
                if error_msg:
                    logs.append(f"⚠️ {error_msg}")
        except:
            pass
    
    # Add questions to logs prominently
    if all_questions:
        logs.append("\n❓ I need some clarification to help you better:")
        for i, question in enumerate(all_questions, 1):
            logs.append(f"  {i}. {question}")
        logs.append("\nPlease answer in the chat below!")

    # ---- Stage 2: Synthesis (force JSON object)
    synthesis_system_prompt = """
You are a 'Proactive Life Manager Agent'. Create a valid JSON object only.

CONTEXT AWARENESS:
- You will receive trip_context and conversation_summary in the payload
- ALWAYS refer to these to maintain continuity about the destination, dates, and user preferences
- If the user asks follow-up questions (e.g., "show me more events"), use the existing trip context
- Remember what the user has already selected or expressed interest in

STRICT FIELD REQUIREMENTS:
- FLIGHTS: airline, flight_number, total_price, currency, out_duration,
  departure_airport, departure_time, arrival_airport, arrival_time, booking_link.
- HOTELS: name, price_per_night (numeric), currency, rating (if available), link,
  latitude, longitude, short description.
- EVENTS: title, start_date, start_time, end_time (infer from 'when' if missing),
  venue name, venue latitude/longitude, ticket link (if available), price (numeric if possible or price_text).

SCHEDULING RULES:
- No overlapping items. Keep ≥30 min buffers between activities; ≥90 min before flights.
- Prefer 2–4 activities per full day. If conflicts occur, keep the best and drop the rest.
  Log drops as 'conflict_removed'.
- IMPORTANT: Include at least 1-2 events/activities in the itinerary for each day of the trip
- Events should be type='activity' in the itinerary

OPTIONS FOR USER SELECTION:
- Include ALL available flights in the 'options' array (not just alternatives)
- Include ALL available events in the 'options' array (not just alternatives)
- Each option should have: type ('flight'|'event'|'hotel'), category (e.g., 'outbound_flight', 'activity_option'), data (full details), and a unique option_id
- The itinerary should only contain confirmed/booked items or be empty initially
- Users will select from options to build their itinerary
- In logs, tell users to select their preferred flights and activities from the options below

OUTPUT SHAPE:
{
  "status": "success" | "needs_clarification" | "error",
  "itinerary": [
    {
      "id": "uuid",
      "title": "string",
      "description": "string",
      "startTime": "YYYY-MM-DDTHH:MM:SS",
      "endTime": "YYYY-MM-DDTHH:MM:SS",
      "type": "travel" | "lodging" | "activity",
      "details": {
        "flight": {...}, "hotel": {...}, "event": {...}
      }
    }
  ],
  "options": [
    {
      "option_id": "uuid",
      "type": "flight" | "event" | "hotel",
      "category": "outbound_flight" | "return_flight" | "activity_option" | "lodging_option",
      "title": "string",
      "description": "string",
      "data": {...},
      "replaces_itinerary_id": "uuid or null"
    }
  ],
  "logs": ["..."],
  "locations": [
    {"name":"...", "latitude":0, "longitude":0, "linkedItineraryId":"..."}
  ]
}

If any tool result indicates 'user_prompt_needed': true, set status to 'needs_clarification' and include suggested_questions in logs.

Respond with JSON only (no fences, no prose).
"""
    synthesis_user_payload = {
        "goal": goal,
        "tool_results": tool_results,
        "execution_logs": logs[-10:],  # recent tail
        "user_context": {
            "city": current_profile.city,
            "timezone": current_profile.timezone,
            "now_utc": now_iso
        },
        "trip_context": trip_context,  # Include extracted trip context
        "conversation_summary": [
            {"role": msg.get("role"), "content": msg.get("content", "")[:200]}  # Truncate for brevity
            for msg in msg.conversation_history[-3:]  # Last 3 messages for context
        ],
        "current_itinerary": msg.itinerary  # Include current itinerary for context
    }

    try:
        synth_msg = claude_client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=4096,
            system=synthesis_system_prompt,
            messages=[
                {"role": "user", "content": json.dumps(synthesis_user_payload, indent=2)},
                {"role": "assistant", "content": "{"},  # force JSON object continuation
            ],
            temperature=0.2,
        )
        final_plan = safe_json_from_prefill_object(synth_msg.content[0].text)

        # Server-side safety: ensure IDs and remove overlaps
        final_plan = ensure_ids(final_plan)
        final_plan = enforce_no_overlaps(final_plan)
        
        # Extract options from tool results if not already in final_plan
        if not final_plan.get("options"):
            final_plan["options"] = []
        
        # Extract ALL flight options
        for result in tool_results:
            if result.get("tool") == "search_flights":
                try:
                    flight_data = json.loads(result.get("result", "{}"))
                    # Get both 'best' and 'other' flights
                    all_flights = []
                    results = flight_data.get("results", {})
                    all_flights.extend(results.get("best", []))
                    all_flights.extend(results.get("other", []))
                    
                    for i, flight in enumerate(all_flights):  # ALL flights
                        if flight.get("total_price"):
                            duration_min = flight.get('out_duration', 0)
                            hours = duration_min // 60
                            mins = duration_min % 60
                            
                            # Extract departure date/time from first leg
                            departure_time = ""
                            arrival_time = ""
                            legs_out = flight.get('legs_out', [])
                            if legs_out and len(legs_out) > 0:
                                first_leg = legs_out[0]
                                departure_time = first_leg.get('departure_time', '')
                                # Get arrival time from last leg for end-to-end time
                                last_leg = legs_out[-1]
                                arrival_time = last_leg.get('arrival_time', '')
                            
                            # Build enhanced title with time
                            title_parts = []
                            if departure_time:
                                title_parts.append(f"Departs {departure_time}")
                            title_parts.append(f"${flight.get('total_price')}")
                            title_parts.append(f"{hours}h {mins}m")
                            title = " • ".join(title_parts)
                            
                            # Build enhanced description
                            desc_parts = []
                            if departure_time and arrival_time:
                                desc_parts.append(f"🕐 {departure_time} → {arrival_time}")
                            desc_parts.append(f"⏱️ Duration: {hours}h {mins}m")
                            desc_parts.append(f"💵 Price: ${flight.get('total_price')} {flight.get('currency', 'USD')}")
                            description = " | ".join(desc_parts)
                            
                            final_plan["options"].append({
                                "option_id": f"flight_option_{i}_{uuid.uuid4().hex[:8]}",
                                "type": "flight",
                                "category": "outbound_flight",
                                "title": title,
                                "description": description,
                                "data": flight,
                                "replaces_itinerary_id": None
                            })
                except Exception as e:
                    logs.append(f"Error extracting flight options: {e}")
        
        # Extract event options
        for result in tool_results:
            if result.get("tool") == "search_events":
                try:
                    event_data = json.loads(result.get("result", "{}"))
                    events = event_data.get("events", [])
                    for i, event in enumerate(events):  # ALL events
                        if event.get("title"):
                            venue_name = event.get("venue", {}).get("name", "")
                            price_text = event.get("price_text", "Free") if event.get("price_text") else ""
                            start_date = event.get("start_date", "")
                            start_time = event.get("start_time", "")
                            
                            # Build description
                            desc_parts = []
                            if venue_name:
                                desc_parts.append(f"📍 {venue_name}")
                            if start_date:
                                desc_parts.append(f"📅 {start_date}")
                            if start_time:
                                desc_parts.append(f"🕒 {start_time}")
                            if price_text:
                                desc_parts.append(f"💵 {price_text}")
                            
                            description = " | ".join(desc_parts) if desc_parts else event.get("description", "")
                            
                            final_plan["options"].append({
                                "option_id": f"event_option_{i}_{uuid.uuid4().hex[:8]}",
                                "type": "event",
                                "category": "activity_option",
                                "title": event.get("title"),
                                "description": description,
                                "data": event,
                                "replaces_itinerary_id": None
                            })
                except Exception as e:
                    logs.append(f"Error extracting event options: {e}")
        
        # Update logs if options were added
        options_count = len(final_plan.get("options", []))
        print(f"DEBUG: Extracted {options_count} total options")
        if final_plan.get("options"):
            final_plan["logs"] = final_plan.get("logs", []) + [
                f"\n✨ Found {len(final_plan['options'])} alternative options for you to choose from!"
            ]
        else:
            print("WARNING: No options in final_plan!")

        ctx.logger.info(final_plan)
        print(f"DEBUG: Returning response with {len(final_plan.get('options', []))} options")

        return AgentPlanResponse(**final_plan)

    except Exception as e:
        logs.append(f"Error in synthesis phase: {e}")
        return AgentPlanResponse(status="error", itinerary=[], logs=logs, locations=[])

# ---- REFINE endpoint (Groq) ----

@agent.on_rest_post("/refine", RefineRequest, AgentPlanResponse)
async def handle_refine_request(ctx: Context, msg: RefineRequest) -> AgentPlanResponse:
    ctx.logger.info(f"Received refinement request with {len(msg.itinerary)} items")

    refinement_prompt = f"""
You are refining a travel itinerary. The user has made changes to their plan.
Your job is to:
1. Validate the itinerary structure
2. Update or add missing location data (latitude/longitude) for any items
3. Ensure all itinerary items have proper IDs and are linked to locations
4. Add helpful suggestions in the logs

Current Itinerary:
{json.dumps(msg.itinerary, indent=2)}

Current Locations:
{json.dumps(msg.locations, indent=2)}

You MUST respond with a single JSON object that matches this structure:
{{
  "status": "success",
  "itinerary": [
    {{
      "id": "string (preserve existing IDs or generate new UUIDs)",
      "title": "string",
      "description": "string",
      "startTime": "string (ISO 8601 format)",
      "endTime": "string (ISO 8601 format, if available)",
      "type": "travel" | "lodging" | "activity"
    }}
  ],
  "logs": ["string (your refinement notes and suggestions)"],
  "locations": [
    {{
      "name": "string",
      "latitude": "number",
      "longitude": "number",
      "linkedItineraryId": "string (must match an itinerary item id)"
    }}
  ]
}}

Rules:
- Preserve user's edits and ordering
- If locations are missing coordinates, estimate reasonable values based on the location name
- Ensure every location has a valid linkedItineraryId
- Remove orphaned locations (locations without matching itinerary items)
- Add new locations for itinerary items that don't have them
- Respond ONLY with the JSON object, no other text
"""
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a travel itinerary refinement assistant. Always respond with valid JSON only."},
                {"role": "user", "content": refinement_prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
        )

        refined_json_text = completion.choices[0].message.content or "{}"

        if "```json" in refined_json_text:
            refined_json_text = refined_json_text.split("```json\n")[1].split("```")[0]
        elif "```" in refined_json_text:
            refined_json_text = refined_json_text.split("```")[1].split("```")[0]

        refined_data = json.loads(refined_json_text)

        # Ensure IDs
        for item in refined_data.get("itinerary", []):
            if not item.get("id"):
                item["id"] = str(uuid.uuid4())

        # Add refinement log
        logs = refined_data.get("logs", []) or []
        logs.insert(0, "Itinerary refined using Groq's fast inference")
        refined_data["logs"] = logs

        # Server-side safety: remove overlaps
        refined_data = enforce_no_overlaps(refined_data)

        return AgentPlanResponse(**refined_data)

    except Exception as e:
        ctx.logger.error(f"Error refining itinerary: {e}")
        return AgentPlanResponse(
            status="error",
            itinerary=msg.itinerary,
            logs=[f"Error in refinement: {e}"],
            locations=msg.locations
        )

# ---- PROFILE endpoints via uAgents ----

class Empty(Model):
    pass

@agent.on_rest_post("/profile/get", Empty, UserProfile)
async def get_profile(ctx: Context, _msg: Empty) -> UserProfile:
    return current_profile

@agent.on_rest_post("/profile/set", UserProfile, UserProfile)
async def set_profile(ctx: Context, profile: UserProfile) -> UserProfile:
    global current_profile
    current_profile = profile
    return current_profile

# =========================
# 6) RUN
# =========================

if __name__ == "__main__":
    agent.run()
