import os
import json
import uuid  # Used to generate unique IDs
import re
from groq import Groq
from serpapi import GoogleSearch
from dotenv import load_dotenv
from uagents import Agent, Context, Model
from uagents.query import query

# --- 1. SETUP: LOAD API KEYS AND CLIENTS ---

# Load variables from your .env file (api keys)
load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file")
if not SERPAPI_API_KEY:
    raise ValueError("SERPAPI_API_KEY not found in .env file")

# Initialize the Groq client
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
    flights: list    # List of flight options (up to 5)


# --- 3. REAL TOOLS: FUNCTIONS THAT CALL EXTERNAL APIS ---

def search_real_hotels(query: str):
    """
    Searches SerpApi for real hotel data.
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
    Searches SerpApi for real flight data.
    Query should include departure city/airport and arrival city/airport.
    Example: "San Francisco to Chicago" or "SFO to ORD"
    """
    print(f"TOOL: Searching flights for '{query}'")
    try:
        from datetime import date, timedelta
        
        # Common airport code mappings
        airport_codes = {
            "san francisco": "SFO", "sf": "SFO", "sfo": "SFO",
            "chicago": "ORD", "chi": "ORD", "ord": "ORD",
            "new york": "JFK", "nyc": "JFK", "jfk": "JFK",
            "los angeles": "LAX", "la": "LAX", "lax": "LAX",
            "miami": "MIA", "mia": "MIA",
            "seattle": "SEA", "sea": "SEA",
            "boston": "BOS", "bos": "BOS",
            "denver": "DEN", "den": "DEN",
            "las vegas": "LAS", "vegas": "LAS", "las": "LAS",
            "atlanta": "ATL", "atl": "ATL",
            "dallas": "DFW", "dfw": "DFW",
            "phoenix": "PHX", "phx": "PHX",
            "houston": "IAH", "iah": "IAH",
        }
        
        # Try to parse the query
        query_lower = query.lower()
        departure_id = "SFO"  # Default
        arrival_id = "ORD"    # Default
        
        # Look for "from X to Y" pattern
        if " to " in query_lower:
            parts = query_lower.split(" to ")
            if len(parts) == 2:
                from_part = parts[0].replace("from", "").strip()
                to_part = parts[1].strip()
                
                # Try to find airport codes
                for city, code in airport_codes.items():
                    if city in from_part:
                        departure_id = code
                    if city in to_part:
                        arrival_id = code
        
        # Default to searching flights for next week
        departure_date = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        print(f"  -> Searching: {departure_id} to {arrival_id} on {departure_date}")
        
        params = {
            "engine": "google_flights",
            "departure_id": departure_id,
            "arrival_id": arrival_id,
            "outbound_date": departure_date,
            "currency": "USD",
            "hl": "en",
            "api_key": SERPAPI_API_KEY
        }
        
        search = GoogleSearch(params)
        results = search.get_dict()
        
        print(f"  -> SerpAPI returned {len(results.get('best_flights', []))} best flights")
        print(f"  -> SerpAPI returned {len(results.get('other_flights', []))} other flights")
        
        # Get top 5 flights
        flights = results.get("best_flights", [])[:5]
        if not flights:
            flights = results.get("other_flights", [])[:5]
        
        print(f"  -> Returning {len(flights)} flights to agent")
        
        # Return the raw data as a JSON string
        return json.dumps(flights)
        
    except Exception as e:
        print(f"Error in search_real_flights: {e}")
        import traceback
        traceback.print_exc()
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
    
    # --- CALL 1: (GROQ) Decompose Goal into a Tool Plan ---
    
    plan_system_prompt = f"""
    You are a planning AI. A user has a goal. Your job is to
    decompose that goal into a series of tool calls.
    The tools you have available are:
    {json.dumps(list(AVAILABLE_TOOLS.keys()), indent=2)}
    
    Tool descriptions:
    - search_hotels: Search for hotel accommodations in a city
    - search_events: Search for events, activities, or attractions in a city
    - search_flights: Search for flights between cities (query format: "from [city] to [city]")
    
    IMPORTANT: If the user's goal involves travel between cities or mentions flights,
    you MUST include a search_flights tool call with a query like "from [departure city] to [arrival city]".

    Respond ONLY with a JSON list of dictionaries, in this exact format:
    [
        {{"tool_name": "name_of_tool", "query": "query_for_that_tool"}}
    ]
    """
    
    try:
        ctx.logger.info("Calling Groq for step 1 (planning)...")
        plan_message = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Use Llama 3.3 70B for planning
            max_tokens=1024,
            messages=[
                {"role": "system", "content": plan_system_prompt},
                {"role": "user", "content": msg.prompt}
            ]
        )
        plan_json_text = plan_message.choices[0].message.content
        ctx.logger.info(f"Groq's Plan: {plan_json_text}")
        
        # Extract JSON array from the response (Claude might add explanatory text)
        # Look for the JSON array pattern [...]
        json_match = re.search(r'\[[\s\S]*\]', plan_json_text)
        if json_match:
            plan_json_text = json_match.group(0)
        
        tool_plan = json.loads(plan_json_text)
    except Exception as e:
        ctx.logger.error(f"Error getting plan from Groq: {e}")
        return AgentPlanResponse(status="error", itinerary=[], logs=[f"Error in planning phase: {e}"], locations=[], flights=[])

    # --- STEP 2: (AGENT) Execute the Tool Plan ---
    
    tool_results = []
    execution_logs = [f"Original Goal: {msg.prompt}", f"Groq's plan: {plan_json_text}"]
    
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

    # --- CALL 2: (GROQ) Synthesize Final Itinerary ---

    synthesis_system_prompt = f"""
    You are a 'Proactive Life Manager Agent'. Your job is to take a user's
    original goal and a list of raw JSON tool results and synthesize them into
    a complete, human-readable itinerary.

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
      ],
      "flights": [
        {{
          "id": "string (generate a unique uuid)",
          "airline": "string (airline name from flights[].flights[].airline)",
          "flightNumber": "string (flight number if available)",
          "departure": "string (departure airport code)",
          "arrival": "string (arrival airport code)",
          "departureTime": "string (departure time)",
          "arrivalTime": "string (arrival time)",
          "duration": "string (flight duration)",
          "price": "number (price in USD)",
          "stops": "number (number of stops)"
        }}
      ]
    }}
    
    - Use the logs I provide as the basis for your own logs.
    - Generate a new, unique ID for EACH itinerary item using a UUID.
    - Be creative and make a logical, user-friendly plan.
    - IMPORTANT: Extract latitude and longitude from the tool data. For hotels,
      it's in `gps_coordinates.latitude`. For events, it might be in
      `venue.gps_coordinates`. If it's missing, make your best estimate.
    - IMPORTANT: If flight data is present in tool results, extract up to 5 flight
      options and include them in the "flights" array. The flight data structure from
      SerpAPI has flights nested like: flights[].flights[] where each flight has:
      * airline (string)
      * flight_number (string)
      * departure_airport.id and arrival_airport.id (airport codes)
      * departure_airport.time and arrival_airport.time (times)
      * duration (in minutes)
      * price (number)
      * airline_logo (optional URL)
      Be sure to extract from this nested structure and format for the frontend.
    - If no flight data is present, set "flights" to an empty array [].
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
        ctx.logger.info("Calling Groq for step 2 (synthesis)...")
        synthesis_message = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile", # Use Llama 3.3 70B for synthesis
            max_tokens=4096,
            messages=[
                {"role": "system", "content": synthesis_system_prompt},
                {"role": "user", "content": synthesis_user_prompt}
            ]
        )
        
        final_plan_json_text = synthesis_message.choices[0].message.content
        
        # Clean the response in case Groq wraps it in markdown
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
        return AgentPlanResponse(status="error", itinerary=[], logs=[f"Error in synthesis phase: {e}"], locations=[], flights=[])

# --- 6. RUN THE AGENT ---

if __name__ == "__main__":
    agent.run()