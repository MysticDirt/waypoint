from uagents import Agent, Context, Model
from typing import List, Dict
from elasticsearch import Elasticsearch
from config import AGENT_SEED, ELASTIC_CLOUD_ID, ELASTIC_API_KEY, BRIGHT_DATA_API_KEY

class EventSearchRequest(Model):
    city: str
    start_date: str
    end_date: str
    categories: List[str] = []

class EventSearchResponse(Model):
    events: List[Dict]
    status: str
    error: str = None

# Initialize Event Search Agent
event_agent = Agent(
    name="event_search_agent",
    seed=AGENT_SEED + "_event",
    port=8003,
)

# Elasticsearch client for event indexing/search
es_client = None

@event_agent.on_event("startup")
async def startup(ctx: Context):
    global es_client
    ctx.logger.info(f"Event Search Agent started with address: {event_agent.address}")
    
    # Initialize Elasticsearch connection
    if ELASTIC_CLOUD_ID and ELASTIC_API_KEY:
        es_client = Elasticsearch(
            cloud_id=ELASTIC_CLOUD_ID,
            api_key=ELASTIC_API_KEY
        )
        ctx.logger.info("Connected to Elasticsearch")

@event_agent.on_message(model=EventSearchRequest)
async def handle_event_search(ctx: Context, sender: str, msg: EventSearchRequest):
    """
    Search for events using Elasticsearch + Bright Data scraping
    """
    ctx.logger.info(f"Searching events in {msg.city} from {msg.start_date} to {msg.end_date}")
    
    try:
        # First, try Elasticsearch for cached/indexed events
        events = await search_events_from_elastic(
            city=msg.city,
            start_date=msg.start_date,
            end_date=msg.end_date,
            categories=msg.categories
        )
        
        # If not enough results, scrape fresh data
        if len(events) < 5:
            scraped_events = await scrape_events_via_bright_data(
                city=msg.city,
                start_date=msg.start_date,
                end_date=msg.end_date
            )
            events.extend(scraped_events)
            
            # Index new events in Elasticsearch for future searches
            if scraped_events and es_client:
                await index_events_to_elastic(scraped_events)
        
        await ctx.send(
            sender,
            EventSearchResponse(
                events=events,
                status="success"
            )
        )
        
    except Exception as e:
        ctx.logger.error(f"Event search error: {e}")
        await ctx.send(
            sender,
            EventSearchResponse(
                events=[],
                status="error",
                error=str(e)
            )
        )

async def search_events_from_elastic(city: str, start_date: str, end_date: str, 
                                     categories: List[str]) -> List[Dict]:
    """
    Search indexed events from Elasticsearch
    """
    if not es_client:
        return []
    
    try:
        query = {
            "bool": {
                "must": [
                    {"match": {"city": city}},
                    {"range": {"date": {"gte": start_date, "lte": end_date}}}
                ]
            }
        }
        
        if categories:
            query["bool"]["should"] = [{"match": {"category": cat}} for cat in categories]
        
        response = es_client.search(
            index="events",
            query=query,
            size=20
        )
        
        return [hit["_source"] for hit in response["hits"]["hits"]]
    except Exception as e:
        print(f"Elasticsearch search error: {e}")
        return []

async def scrape_events_via_bright_data(city: str, start_date: str, end_date: str) -> List[Dict]:
    """
    Scrape events from Eventbrite, Meetup, etc. using Bright Data
    """
    if not BRIGHT_DATA_API_KEY:
        return []
    
    # TODO: Implement Bright Data scraping for events
    return []

async def index_events_to_elastic(events: List[Dict]):
    """
    Index new events into Elasticsearch
    """
    if not es_client:
        return
    
    try:
        for event in events:
            es_client.index(index="events", document=event)
    except Exception as e:
        print(f"Elasticsearch indexing error: {e}")

if __name__ == "__main__":
    event_agent.run()