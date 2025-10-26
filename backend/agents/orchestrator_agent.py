from uagents import Agent, Context, Model, Bureau
from typing import List, Dict
import anthropic
from groq import Groq
from config import (
    AGENT_SEED, ANTHROPIC_API_KEY, GROQ_API_KEY, 
    CLAUDE_MODEL, GROQ_MODEL
)

class TripPlanRequest(Model):
    prompt: str

class TripPlanResponse(Model):
    status: str
    itinerary: List[Dict]
    flights: List[Dict]
    events: List[Dict]
    logs: List[str]
    locations: List[Dict]

# Initialize Orchestrator Agent
orchestrator = Agent(
    name="trip_orchestrator",
    seed=AGENT_SEED + "_orchestrator",
    port=8001,
)

# AI clients
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

@orchestrator.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"Trip Orchestrator started with address: {orchestrator.address}")

@orchestrator.on_message(model=TripPlanRequest)
async def handle_trip_plan(ctx: Context, sender: str, msg: TripPlanRequest):
    """
    Main orchestration logic:
    1. Use Groq for fast initial response
    2. Parse user intent with Claude
    3. Delegate to specialized agents (flight, event)
    4. Synthesize final itinerary with Claude
    """
    logs = []
    
    try:
        # Step 1: Fast acknowledgment with Groq
        logs.append("Processing your request...")
        quick_response = await get_groq_response(msg.prompt)
        logs.append(f"Understanding: {quick_response}")
        
        # Step 2: Extract structured data with Claude
        logs.append("Analyzing trip requirements...")
        trip_details = await extract_trip_details_with_claude(msg.prompt)
        logs.append(f"Destination: {trip_details.get('destination', 'Unknown')}")
        
        # Step 3: Delegate to specialized agents
        # TODO: Send messages to flight_agent and event_agent
        flights = []
        events = []
        
        # Step 4: Synthesize final itinerary with Claude
        logs.append("Creating your personalized itinerary...")
        itinerary = await create_itinerary_with_claude(trip_details, flights, events)
        
        # Extract locations for map
        locations = extract_locations(itinerary, trip_details)
        
        await ctx.send(
            sender,
            TripPlanResponse(
                status="success",
                itinerary=itinerary,
                flights=flights,
                events=events,
                logs=logs,
                locations=locations
            )
        )
        
    except Exception as e:
        ctx.logger.error(f"Trip planning error: {e}")
        logs.append(f"Error: {str(e)}")
        await ctx.send(
            sender,
            TripPlanResponse(
                status="error",
                itinerary=[],
                flights=[],
                events=[],
                logs=logs,
                locations=[]
            )
        )

async def get_groq_response(prompt: str) -> str:
    """
    Get fast initial response using Groq
    """
    if not groq_client:
        return "Processing your trip request..."
    
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful travel assistant. Provide a brief acknowledgment of the user's trip request."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Groq error: {e}")
        return "Processing your trip request..."

async def extract_trip_details_with_claude(prompt: str) -> Dict:
    """
    Use Claude to extract structured trip details from natural language
    """
    if not claude_client:
        return {"destination": "Unknown", "dates": [], "interests": []}
    
    try:
        message = claude_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"""Extract trip details from this request and return as JSON:
{prompt}

Return format:
{{
    "origin": "city name",
    "destination": "city name",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "interests": ["category1", "category2"],
    "budget": "low/medium/high"
}}"""
                }
            ]
        )
        
        # Parse Claude's response (should be JSON)
        import json
        return json.loads(message.content[0].text)
    except Exception as e:
        print(f"Claude extraction error: {e}")
        return {"destination": "Unknown", "dates": [], "interests": []}

async def create_itinerary_with_claude(trip_details: Dict, flights: List[Dict], 
                                       events: List[Dict]) -> List[Dict]:
    """
    Use Claude to synthesize all data into a coherent itinerary
    """
    if not claude_client:
        return []
    
    try:
        context = f"""
Trip Details: {trip_details}
Available Flights: {flights}
Available Events: {events}

Create a detailed day-by-day itinerary in JSON format:
[
    {{
        "day": 1,
        "date": "YYYY-MM-DD",
        "title": "Day title",
        "activities": ["activity1", "activity2"],
        "notes": "Additional notes"
    }}
]
"""
        
        message = claude_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": context}]
        )
        
        import json
        return json.loads(message.content[0].text)
    except Exception as e:
        print(f"Claude itinerary error: {e}")
        return []

def extract_locations(itinerary: List[Dict], trip_details: Dict) -> List[Dict]:
    """
    Extract location coordinates for map visualization
    """
    # TODO: Geocode locations from itinerary
    return []

if __name__ == "__main__":
    orchestrator.run()