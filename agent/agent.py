import os
import json
import uuid  # Used to generate unique IDs
import anthropic
from groq import Groq
from serpapi import GoogleSearch
from dotenv import load_dotenv
from uagents import Agent, Context, Model
from uagents.query import query

from flights_tool import find_flights

# --- 1. SETUP: LOAD API KEYS AND CLIENTS ---

# Load variables from your .env file (api keys)
load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in .env file")
if not SERPAPI_API_KEY:
    raise ValueError("SERPAPI_API_KEY not found in .env file")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file")

# Initialize the Anthropic (Claude) client
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Initialize the Groq client for fast refinement
groq_client = Groq(api_key=GROQ_API_KEY)


# --- 2. DATA MODELS: DEFINE AGENT'S INPUT/OUTPUT ---

# This model defines the data we expect to receive from the backend
class PlanRequest(Model):
    prompt: str  # e.g., "Plan a cheap cultural weekend in Chicago"

# This model defines the final, structured data we will send back
class AgentPlanResponse(Model):
    status: str      # "success" or "error"
    itinerary: list  # List of itinerary items
    logs: list       # List of strings for debugging/showing thought process
    locations: list  # List of location objects for the map

# This model defines the data for refining an existing itinerary
class RefineRequest(Model):
    itinerary: list  # Current itinerary items (user may have edited)
    locations: list  # Current location data


# --- 3. REAL TOOLS: FUNCTIONS THAT CALL EXTERNAL APIS ---

def search_real_hotels(query: str):
    """
    Searches SerpApi for real hotel data.
    Now returns up to 8 hotels by default (increased from 3) to give users more options.
    
    Args:
        query: Search query for hotels (e.g., "hotels in Chicago", "budget hotels Boston")
        max_results: Maximum number of hotels to return (default: 8)
    """
    print(f"TOOL: Searching hotels for '{query}'")
    try:
        # Get today's and tomorrow's date for the search
        from datetime import date, timedelta
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        params = {
            "engine": "google_hotels",
            "q": query,
            "api_key": SERPAPI_API_KEY,
            "check_in_date": today.strftime("%Y-%m-%d"),
            "check_out_date": tomorrow.strftime("%Y-%m-%d"),
            "currency": "USD"
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # Get top 3 properties to avoid overwhelming the LLM
        properties = results.get("properties", [])[:3]
        
        # Return the raw data as a JSON string
        return json.dumps(properties)
        
    except Exception as e:
        print(f"Error in search_real_hotels: {e}")
        return json.dumps({"error": str(e)})

def search_real_events(query: str):
    """
    Searches SerpApi for real event data.
    Now returns up to 10 events by default (increased from 3) to give users more options.
    
    Args:
        query: Search query for events (e.g., "concerts in Chicago", "cultural events Boston")
        max_results: Maximum number of events to return (default: 10, can go higher)
    """
    print(f"TOOL: Searching events for '{query}'")
    try:
        params = {
            "engine": "google_events",
            "q": query,
            "api_key": SERPAPI_API_KEY,
            "hl": "en",
            "gl": "us"
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # Get top 3 events
        events = results.get("events_results", [])[:3]
        
        # Return the raw data as a JSON string
        return json.dumps(events)
        
    except Exception as e:
        print(f"Error in search_real_events: {e}")
        return json.dumps({"error": str(e)})

def search_real_flights(query: str):
    """
    Searches SerpApi (Google Flights) for real flight data.
    Accepts natural language like:
      - "LAX to BOS depart 2025-12-20 return 2025-12-28 nonstop economy 1 seat USD"
      - "SFO->JFK 2025-11-15 2025-11-22 business 2 seats"
      - "Austin to New York 2025-12-20 nonstop"
    Returns a compact JSON string (limit top 3 per bucket).
    """
    print(f"TOOL: Searching flights for '{query}'")
    try:
        import re
        from datetime import date

        # --- Parse fields from query ---
        # origin/destination (IATA codes or city names)
        # e.g., "LAX to BOS", "SFO->JFK", "Austin to New York"
        od_match = re.search(r"\b([A-Za-z]{3,}?)\b\s*(?:to|->|—|-)\s*\b([A-Za-z]{3,}?)\b", query, flags=re.IGNORECASE)
        origin = od_match.group(1).upper() if od_match else None
        destination = od_match.group(2).upper() if od_match else None

        # dates: first YYYY-MM-DD is depart, second (optional) is return
        date_matches = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", query)
        depart_date = date_matches[0] if len(date_matches) >= 1 else None
        return_date = date_matches[1] if len(date_matches) >= 2 else None

        # nonstop
        non_stop = bool(re.search(r"\bnon[-\s]?stop\b", query, flags=re.IGNORECASE))

        # cabin
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

        # seats
        seats = 1
        m_seats = re.search(r"\b(\d+)\s*(?:seats?|adults?)\b", query, flags=re.IGNORECASE)
        if m_seats:
            seats = max(1, int(m_seats.group(1)))

        # currency
        currency = "USD"
        m_ccy = re.search(r"\b(USD|EUR|GBP|CAD|AUD|JPY|INR|CNY|KRW|MXN)\b", query, flags=re.IGNORECASE)
        if m_ccy:
            currency = m_ccy.group(1).upper()

        # Basic validation
        if not origin or not destination or not depart_date:
            return json.dumps({
                "error": "Missing required fields. Provide 'ORIGIN to DEST', and a 'YYYY-MM-DD' depart date.",
                "hint": "Example: 'LAX to BOS depart 2025-12-20 return 2025-12-28 nonstop economy 1 seat USD'"
            })

        # Call your normalized SerpApi wrapper
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

        # Trim to top 3 per bucket and keep key fields only
        def shrink(bucket):
            trimmed = []
            for f in (bucket or [])[:3]:
                trimmed.append({
                    "title": f.get("title"),
                    "total_price": f.get("total_price"),
                    "currency": f.get("currency"),
                    "out_duration": f.get("out_duration"),
                    "ret_duration": f.get("ret_duration"),
                    "legs_out": [
                        {
                            "airline": s.get("airline"),
                            "flight_number": s.get("flight_number"),
                            "departure_airport": s.get("departure_airport"),
                            "departure_time": s.get("departure_time"),
                            "arrival_airport": s.get("arrival_airport"),
                            "arrival_time": s.get("arrival_time"),
                            "duration": s.get("duration"),
                            "layovers": s.get("layovers", []),
                        } for s in f.get("legs_out", [])
                    ],
                    "booking_links": (f.get("booking_links") or [])[:2],  # keep at most 2
                })
            return trimmed

        result_payload = {
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
            "results": {
                "best": shrink(data.get("best")),
                "other": shrink(data.get("other")),
                "best_return": shrink(data.get("best_return")),
                "other_return": shrink(data.get("other_return")),
            }
        }
        return json.dumps(result_payload)

    except Exception as e:
        print(f"Error in search_real_flights: {e}")
        return json.dumps({"error": str(e)})


# This dictionary maps the tool *name* (used by the LLM) to the *function*
AVAILABLE_TOOLS = {
    "search_hotels": search_real_hotels,
    "search_events": search_real_events,
    "search_flights": search_real_flights,
}


# --- 4. AGENT INITIALIZATION ---

# Initialize your Fetch.ai uAgent
agent = Agent(
    name="proactive_life_manager_agent",
    port=8001,
    seed="my_cal_hacks_secret_seed_phrase" # Change this to a unique phrase
)

@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info("Agent started!")
    ctx.logger.info("Waiting for planning requests...")


# --- 5. THE "BRAIN": AGENT'S MAIN LOGIC HANDLER ---

@agent.on_rest_post("/plan", PlanRequest, AgentPlanResponse)
async def handle_plan_request(ctx: Context, msg: PlanRequest) -> AgentPlanResponse:
    """
    This function is the main entry point.
    It receives a prompt, creates a plan, executes tools, and synthesizes a result.
    """
    ctx.logger.info(f"Received planning request: '{msg.prompt}'")
    
    # --- CALL 1: (CLAUDE) Decompose Goal into a Tool Plan ---
    
    plan_system_prompt = f"""
    You are a planning AI. A user has a goal. Your job is to
    decompose that goal into a series of tool calls.
    The tools you have available are:
    {json.dumps(list(AVAILABLE_TOOLS.keys()), indent=2)}
    
    IMPORTANT for search_flights:
    - The query MUST include: origin city/airport, destination city/airport, and departure date in YYYY-MM-DD format
    - Extract dates from natural language (e.g., "November 1st" -> "2025-11-01")
    - If the user doesn't provide specific dates or locations, include what you can extract
    - Format: "ORIGIN to DESTINATION depart YYYY-MM-DD return YYYY-MM-DD"
    - Example: "New York to San Jose depart 2025-11-01 return 2025-11-03"

    Respond ONLY with a JSON list of dictionaries, in this exact format:
    [
        {{"tool_name": "name_of_tool", "query": "query_for_that_tool"}}
    ]
    """
    
    try:
        ctx.logger.info("Calling Claude for step 1 (planning)...")
        plan_message = claude_client.messages.create(
            model="claude-3-5-haiku-20241022",  # Use Claude 3.5 Haiku for planning
            max_tokens=1024,
            system=plan_system_prompt,
            messages=[
                {"role": "user", "content": msg.prompt}
            ]
        )
        plan_json_text = plan_message.content[0].text
        ctx.logger.info(f"Claude's Plan: {plan_json_text}")
        tool_plan = json.loads(plan_json_text)
    except Exception as e:
        ctx.logger.error(f"Error getting plan from Claude: {e}")
        return AgentPlanResponse(status="error", itinerary=[], logs=[f"Error in planning phase: {e}"], locations=[])

    # --- STEP 2: (AGENT) Execute the Tool Plan ---
    
    tool_results = []
    execution_logs = [f"Original Goal: {msg.prompt}", f"Claude's plan: {plan_json_text}"]
    
    ctx.logger.info("Executing tool plan...")
    for task in tool_plan:
        tool_name = task.get("tool_name")
        tool_query = task.get("query")
        
        if tool_name in AVAILABLE_TOOLS:
            try:
                # Call the actual tool function (e.g., search_real_hotels)
                result_data = AVAILABLE_TOOLS[tool_name](tool_query)
                tool_results.append({
                    "tool": tool_name,
                    "query": tool_query,
                    "result": result_data
                })
                execution_logs.append(f"Successfully called {tool_name} with '{tool_query}'")
            except Exception as e:
                ctx.logger.error(f"Error executing tool {tool_name}: {e}")
                tool_results.append({"tool": tool_name, "result": f"Error: {e}"})
        else:
            ctx.logger.warning(f"LLM tried to call unknown tool: '{tool_name}'")
            execution_logs.append(f"Warning: Unknown tool '{tool_name}'")

    # --- CALL 2: (CLAUDE) Synthesize Final Itinerary ---

    synthesis_system_prompt = f"""
    You are a 'Proactive Life Manager Agent'. Your job is to take a user's
    original goal and a list of raw JSON tool results and synthesize them into
    a complete, human-readable itinerary.
    
    IMPORTANT: If any tool returns an error with "user_prompt_needed": true, you should:
    1. Set status to "needs_clarification" instead of "success"
    2. Include the suggested_questions in the logs for the user to see
    3. Create a minimal itinerary with what you DO have
    4. Clearly indicate in the logs what information is missing

    You MUST respond with a single JSON object that matches this structure:
    {{
      "status": "success",
      "itinerary": [
        {{
          "id": "string (generate a unique uuid)",
          "title": "string (e.g., 'Check into Hotel')",
          "description": "string (e.g., 'Check into The Drake Hotel')",
          "startTime": "string (ISO 8601 format, e.g., 2025-10-26T15:00:00)",
          "type": "travel" | "lodging" | "activity"
        }}
      ],
      "logs": ["string (a log of your thought process)"],
      "locations": [
        {{
          "name": "string (e.g., 'The Drake Hotel')",
          "latitude": "number (get from tool data, e.g., 'gps_coordinates.latitude')",
          "longitude": "number (get from tool data, e.g., 'gps_coordinates.longitude')",
          "linkedItineraryId": "string (must match one of the itinerary item ids you just generated)"
        }}
      ]
    }}
    
    - Use the logs I provide as the basis for your own logs.
    - Generate a new, unique ID for EACH itinerary item using a UUID.
    - Be creative and make a logical, user-friendly plan.
    - IMPORTANT: When you receive multiple events from the search results, include them as "options"
      in the itinerary item so users can choose which event they prefer.
    - For events, create ONE itinerary item with multiple options listed in the "options" array.
    - CRITICAL: Include ALL available details in the options array:
      * For events: title, description, venue, time, date, ticket_info, link, price if available
      * For hotels: name, description, price, currency, rating, reviews, amenities, link
      * For flights: airline, price, duration, departure/arrival times, booking links
    - The tool results contain enriched data with prices, ratings, and other details - USE THEM!
    - Look for data in nested structures like "hotels", "events", "results" arrays in the tool output.
    - IMPORTANT: Extract latitude and longitude from the tool data. For hotels,
      it's in `gps_coordinates.latitude`. For events, it might be in
      `venue.gps_coordinates`. If it's missing, make your best estimate.
    - The final response MUST be ONLY the JSON object, with no other text.
    """
    
    synthesis_user_prompt = f"""
    Original Goal: "{msg.prompt}"
    
    Tool Results (Raw JSON):
    {json.dumps(tool_results, indent=2)}
    
    Execution Logs:
    {json.dumps(execution_logs, indent=2)}

    Now, generate the final AgentPlanResponse JSON.
    """
    
    try:
        ctx.logger.info("Calling Claude for step 2 (synthesis)...")
        synthesis_message = claude_client.messages.create(
            model="claude-3-5-haiku-20241022", # Use Claude 3.5 Haiku for synthesis
            max_tokens=4096,
            system=synthesis_system_prompt,
            messages=[
                {"role": "user", "content": synthesis_user_prompt}
            ]
        )
        
        final_plan_json_text = synthesis_message.content[0].text
        
        # Clean the response in case Claude wraps it in markdown
        if "```json" in final_plan_json_text:
             final_plan_json_text = final_plan_json_text.split("```json\n")[1].split("```")[0]
        
        ctx.logger.info("Successfully synthesized final plan.")
        
        final_plan_data = json.loads(final_plan_json_text)
        
        # --- Final Data Integrity Check ---
        # Ensure all itinerary items have unique IDs
        for item in final_plan_data.get("itinerary", []):
            if "id" not in item or not item["id"]:
                item["id"] = str(uuid.uuid4())
        
        # Return the successful response back to the backend
        return AgentPlanResponse(**final_plan_data)
        
    except Exception as e:
        ctx.logger.error(f"Error synthesizing final plan: {e}")
        return AgentPlanResponse(status="error", itinerary=[], logs=[f"Error in synthesis phase: {e}"], locations=[])


# --- 5B. REFINEMENT HANDLER: USING GROQ FOR FAST ITERATION ---

@agent.on_rest_post("/refine", RefineRequest, AgentPlanResponse)
async def handle_refine_request(ctx: Context, msg: RefineRequest) -> AgentPlanResponse:
    """
    This function handles refinement of an existing itinerary.
    It uses Groq's fast LLM inference to quickly update locations and validate the itinerary.
    """
    ctx.logger.info(f"Received refinement request with {len(msg.itinerary)} items")
    
    refinement_logs = [f"Refining itinerary with {len(msg.itinerary)} items"]
    
    # --- Use Groq for fast refinement ---
    # Groq is ideal here because refinement needs to be quick and responsive
    
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
        ctx.logger.info("Calling Groq for fast refinement...")
        
        # Use Groq's llama-3.3-70b-versatile for fast, high-quality refinement
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Fast and capable model
            messages=[
                {
                    "role": "system",
                    "content": "You are a travel itinerary refinement assistant. Always respond with valid JSON only."
                },
                {
                    "role": "user",
                    "content": refinement_prompt
                }
            ],
            temperature=0.3,  # Lower temperature for more consistent refinement
            max_tokens=4096,
        )
        
        refined_json_text = completion.choices[0].message.content
        
        # Clean the response in case it's wrapped in markdown
        if "```json" in refined_json_text:
            refined_json_text = refined_json_text.split("```json\n")[1].split("```")[0]
        elif "```" in refined_json_text:
            refined_json_text = refined_json_text.split("```")[1].split("```")[0]
        
        ctx.logger.info("Successfully refined itinerary with Groq.")
        
        refined_data = json.loads(refined_json_text)
        
        # --- Data Integrity Check ---
        # Ensure all itinerary items have unique IDs
        for item in refined_data.get("itinerary", []):
            if "id" not in item or not item["id"]:
                item["id"] = str(uuid.uuid4())
        
        # Add refinement log
        refined_data.get("logs", []).insert(0, "Itinerary refined using Groq's fast inference")
        
        return AgentPlanResponse(**refined_data)
        
    except Exception as e:
        ctx.logger.error(f"Error refining itinerary: {e}")
        # On error, return the original data with error status
        return AgentPlanResponse(
            status="error",
            itinerary=msg.itinerary,
            logs=[f"Error in refinement: {e}"],
            locations=msg.locations
        )


# --- 6. RUN THE AGENT ---

if __name__ == "__main__":
    agent.run()