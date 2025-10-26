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

class AgentPlanResponse(Model):
    status: str           # "success" | "needs_clarification" | "error"
    itinerary: list       # List[dict] of itinerary items
    logs: list            # List[str] for trace / notes
    locations: list       # List[dict] map markers

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

def search_real_events(query: str) -> str:
    """
    Event search that defaults to the user's city from current_profile.
    Adds SerpApi 'location' and post-filters to that city when possible.
    """
    print(f"TOOL: Searching events for '{query}'")
    try:
        import re
        from datetime import timedelta

        # Extract an explicit YYYY-MM-DD..YYYY-MM-DD range if present
        range_text = None
        m = re.search(r"(\d{4}-\d{2}-\d{2})\s*[\.\-–]+\s*(\d{4}-\d{2}-\d{2})", query)
        if m:
            range_text = f"{m.group(1)}..{m.group(2)}"

        # Default event location is the user's city (e.g., "Berkeley, CA, USA")
        default_location = current_profile.city or "United States"

        params = {
            "engine": "google_events",
            "q": query,
            "api_key": SERPAPI_API_KEY,
            "hl": "en",
            "gl": "us",
            "location": default_location,   # <— use user's city as SerpApi location bias
        }
        if range_text:
            params["date"] = range_text

        results = GoogleSearch(params).get_dict()
        events = results.get("events_results", [])[:20]

        def add_year_if_missing(md: str | None) -> str | None:
            if not md:
                return None
            # Pass through full dates
            if re.match(r"^\d{4}-\d{2}-\d{2}$", md):
                return md
            # Try "Dec 19" -> current/next year
            try:
                dt = datetime.strptime(md + f" {datetime.utcnow().year}", "%b %d %Y")
                if dt < datetime.utcnow() - timedelta(days=30):
                    dt = dt.replace(year=dt.year + 1)
                return dt.strftime("%Y-%m-%d")
            except Exception:
                return None

        def parse_times(e):
            d = e.get("date", {})
            start_date = add_year_if_missing(d.get("start_date"))
            end_date = add_year_if_missing(d.get("end_date") or d.get("start_date"))
            start_time = d.get("start_time")
            end_time = d.get("end_time")
            when = (d.get("when") or "") if isinstance(d, dict) else ""
            if not end_time and "–" in when:
                mm = re.search(r"–\s*([0-9]{1,2}:[0-9]{2}\s*[AP]M)", when)
                if mm:
                    end_time = mm.group(1)
            return start_date, end_date, start_time, end_time

        # City-aware filter (match first token of city; tolerant)
        city_token = (default_location.split(",")[0] or "").strip().lower()

        def is_in_user_city(e):
            v = e.get("venue") or {}
            name = (v.get("name") or "").lower()
            addr = (v.get("address") or "").lower()
            blob = name + " " + addr
            return (city_token and city_token in blob) or (default_location.lower() in blob)

        def parse_price(e):
            tix = e.get("ticket_info", []) or []
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

        normalized = []
        for e in events:
            # Keep only items that look like they're in/near the user's city
            if not is_in_user_city(e):
                continue
            start_date, end_date, start_time, end_time = parse_times(e)
            ex_price, ccy, price_text, ticket_link = parse_price(e)
            venue = e.get("venue", {}) if isinstance(e.get("venue"), dict) else {}
            coords = venue.get("gps_coordinates") or {}

            normalized.append({
                "title": e.get("title"),
                "description": e.get("description"),
                "start_date": start_date,
                "end_date": end_date,
                "start_time": start_time,
                "end_time": end_time,
                "venue": {
                    "name": venue.get("name"),
                    "address": venue.get("address"),
                    "latitude": coords.get("latitude"),
                    "longitude": coords.get("longitude"),
                },
                "price": ex_price,
                "price_text": price_text,
                "currency": ccy or "USD",
                "link": ticket_link or e.get("link"),
                "source": e.get("source"),
            })

        normalized = [n for n in normalized if n["title"] and n["start_date"]][:12]
        if not normalized:
            return json.dumps({
                "error": f"No events found near {default_location} for that query",
                "user_prompt_needed": True,
                "suggested_questions": [
                    f"Should I broaden beyond {default_location}?",
                    "Any specific neighborhoods or venues?",
                    "Should I extend the date window by ±1 day?"
                ]
            })

        return json.dumps({"events": normalized})

    except Exception as e:
        print(f"Error in search_real_events: {e}")
        return json.dumps({"error": str(e), "user_prompt_needed": True})

def search_real_flights(query: str) -> str:
    """
    Searches SerpApi (Google Flights) via find_flights and returns a compact JSON.
    Robust against schema drift: only iterates lists of dicts, skips bad items.
    """
    print(f"TOOL: Searching flights for '{query}'")
    try:
        import re

        # --- Parse query ---
        od_match = re.search(r"\b([A-Za-z]{3,}?)\b\s*(?:to|->|—|-)\s*\b([A-Za-z]{3,}?)\b", query, flags=re.IGNORECASE)
        origin = od_match.group(1).upper() if od_match else None
        destination = od_match.group(2).upper() if od_match else None

        

        date_matches = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", query)
        depart_date = date_matches[0] if len(date_matches) >= 1 else None
        return_date = date_matches[1] if len(date_matches) >= 2 else None

        non_stop = bool(re.search(r"\bnon[-\s]?stop\b", query, flags=re.IGNORECASE))

        # If ORIGIN missing, try user's home airport from profile city
        if not origin:
            origin = infer_home_airport(current_profile.city)

        # If DEST is *clearly* a city name (not IATA) with spaces, you can let find_flights fail politely.
        # (Optional: add your own city->IATA mapping for common destinations)

        ...
        if not origin or not destination or not depart_date:
            # Build dynamic hints using the profile city if we inferred nothing
            hints = [
                "What cities or airports are you flying between?",
                "What is your departure date in YYYY-MM-DD?",
                "Do you need a return date?"
            ]
            if not origin and current_profile.city:
                hints.insert(0, f"What's your preferred airport near {current_profile.city}?")
            return json.dumps({
                "error": "Missing origin/destination/depart_date",
                "user_prompt_needed": True,
                "suggested_questions": hints
            })

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
            return json.dumps({
                "error": "Missing origin/destination/depart_date",
                "user_prompt_needed": True,
                "suggested_questions": [
                    "What cities or airports are you flying between?",
                    "What is your departure date in YYYY-MM-DD?",
                    "Do you need a return date?"
                ]
            })

        # --- Call wrapper ---
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

        # --- Robust extraction helpers ---
        def _as_list(x):
            # Accept only lists; if dict with 'flights', use that; else empty
            if isinstance(x, list):
                return x
            if isinstance(x, dict) and isinstance(x.get("flights"), list):
                return x["flights"]
            return []

        def _safe_dicts(items):
            # Keep only dict items
            return [i for i in items if isinstance(i, dict)]

        def shrink(bucket_like):
            items = _safe_dicts(_as_list(bucket_like))[:3]
            trimmed = []
            for f in items:
                # Defensive gets (all keys optional)
                legs_out = []
                for s in _safe_dicts(f.get("legs_out") or []):
                    legs_out.append({
                        "airline": s.get("airline"),
                        "flight_number": s.get("flight_number"),
                        "departure_airport": s.get("departure_airport"),
                        "departure_time": s.get("departure_time"),
                        "arrival_airport": s.get("arrival_airport"),
                        "arrival_time": s.get("arrival_time"),
                        "duration": s.get("duration"),
                        "layovers": s.get("layovers") or [],
                    })
                booking_links = []
                for bl in _safe_dicts(f.get("booking_links") or []):
                    booking_links.append({
                        "provider": bl.get("provider"),
                        "link": bl.get("link"),
                        "price": bl.get("price")
                    })
                trimmed.append({
                    "title": f.get("title"),
                    "total_price": f.get("total_price"),
                    "currency": f.get("currency"),
                    "out_duration": f.get("out_duration"),
                    "ret_duration": f.get("ret_duration"),
                    "legs_out": legs_out,
                    "booking_links": booking_links[:2],
                })
            return trimmed

        # Some environments accidentally serialize/deserialize the wrapper output;
        # guard in case `data` is a JSON string.
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}

        results_obj = {
            "best": shrink(data.get("best")),
            "other": shrink(data.get("other")),
            "best_return": shrink(data.get("best_return")),
            "other_return": shrink(data.get("other_return")),
        }

        # If truly empty, signal clarifications
        if not any(results_obj.values()):
            return json.dumps({
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

        return json.dumps({
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
        # Never throw; always return JSON so the synthesizer can react.
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

    # ---- Stage 1: Planning (force JSON array)
    plan_system_prompt = f"""
You are a planning AI. Output a JSON array ONLY. No prose, no notes, no markdown.

Rules:
- If the user does not specify an ORIGIN airport for flights, use the user's home metro based on profile (e.g., {current_profile.city}) and prefer the primary airport (use our heuristic).
- For events, default search 'location' to the user's city: {current_profile.city}.
- Never pick dates in the past; if ambiguous, choose the next future Fri–Sun weekend (4–8 weeks out).
- Flights query MUST include origin, destination, and a future depart date (YYYY-MM-DD).
- If unsure about return, include a best-guess (Fri–Sun).
- Tools you can call: {json.dumps(list(AVAILABLE_TOOLS.keys()))}

Output format:
[
  {{"tool_name": "search_flights", "query": "SFO to SEA depart 2025-11-21 return 2025-11-23"}},
  {{"tool_name": "search_hotels",  "query": "Seattle downtown budget"}},
  {{"tool_name": "search_events",  "query": "Seattle indoor events Nov 21-23"}}
]
"""
    try:
        logs.append("Planning with Claude…")
        plan_message = claude_client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=plan_system_prompt,
            messages=[
                {"role": "user", "content": context_prefix + goal},
                {"role": "assistant", "content": "["},  # force JSON array continuation
            ],
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

    # ---- Stage 2: Synthesis (force JSON object)
    synthesis_system_prompt = """
You are a 'Proactive Life Manager Agent'. Create a valid JSON object only.

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
        }
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

        ctx.logger.info(final_plan)

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
