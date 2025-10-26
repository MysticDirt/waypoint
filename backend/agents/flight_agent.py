from uagents import Agent, Context, Model
from typing import List, Dict
import aiohttp
from config import AGENT_SEED, BRIGHT_DATA_API_KEY, COMPOSIO_API_KEY

class FlightSearchRequest(Model):
    origin: str
    destination: str
    departure_date: str
    return_date: str = None
    passengers: int = 1

class FlightSearchResponse(Model):
    flights: List[Dict]
    status: str
    error: str = None

# Initialize Flight Search Agent
flight_agent = Agent(
    name="flight_search_agent",
    seed=AGENT_SEED + "_flight",
    port=8002,
)

@flight_agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"Flight Search Agent started with address: {flight_agent.address}")

@flight_agent.on_message(model=FlightSearchRequest)
async def handle_flight_search(ctx: Context, sender: str, msg: FlightSearchRequest):
    """
    Search for flights using Bright Data web scraping + Composio API routing
    """
    ctx.logger.info(f"Searching flights: {msg.origin} -> {msg.destination}")
    
    try:
        # Use Composio to route to flight APIs (Skyscanner, Google Flights, etc.)
        flights = await search_flights_via_composio(
            origin=msg.origin,
            destination=msg.destination,
            departure_date=msg.departure_date,
            return_date=msg.return_date,
            passengers=msg.passengers
        )
        
        # If Composio fails, fallback to Bright Data scraping
        if not flights:
            flights = await scrape_flights_via_bright_data(
                origin=msg.origin,
                destination=msg.destination,
                departure_date=msg.departure_date
            )
        
        await ctx.send(
            sender,
            FlightSearchResponse(
                flights=flights,
                status="success"
            )
        )
        
    except Exception as e:
        ctx.logger.error(f"Flight search error: {e}")
        await ctx.send(
            sender,
            FlightSearchResponse(
                flights=[],
                status="error",
                error=str(e)
            )
        )

async def search_flights_via_composio(origin: str, destination: str, departure_date: str, 
                                      return_date: str = None, passengers: int = 1) -> List[Dict]:
    """
    Use Composio to route flight search requests to multiple APIs
    """
    # TODO: Implement Composio API integration
    # This would connect to Skyscanner, Amadeus, or other flight APIs
    return []

async def scrape_flights_via_bright_data(origin: str, destination: str, departure_date: str) -> List[Dict]:
    """
    Fallback: Use Bright Data to scrape flight information
    """
    if not BRIGHT_DATA_API_KEY:
        return []
    
    # TODO: Implement Bright Data scraping
    # This would scrape Google Flights, Kayak, etc.
    return []

if __name__ == "__main__":
    flight_agent.run()