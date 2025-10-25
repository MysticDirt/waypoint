import os
import json
import uuid  # Used to generate unique IDs
import anthropic
from serpapi import GoogleSearch
from dotenv import load_dotenv
from uagents import Agent, Context, Model
from uagents.query import query

# --- 1. SETUP: LOAD API KEYS AND CLIENTS ---

# Load variables from your .env file (api keys)
load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY")

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in .env file")
if not SERPAPI_API_KEY:
    raise ValueError("SERPAPI_API_KEY not found in .env file")

# Initialize the Anthropic (Claude) client
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


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

# This dictionary maps the tool *name* (used by the LLM) to the *function*
AVAILABLE_TOOLS = {
    "search_hotels": search_real_hotels,
    "search_events": search_real_events,
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

# --- 6. RUN THE AGENT ---

if __name__ == "__main__":
    agent.run()