"""
Run all Fetch.ai agents together using Bureau
"""
from uagents import Bureau
from agents.orchestrator_agent import orchestrator
from agents.flight_agent import flight_agent
from agents.event_agent import event_agent

if __name__ == "__main__":
    # Create a bureau to run all agents together
    bureau = Bureau(port=8001)
    
    # Add all agents to the bureau
    bureau.add(orchestrator)
    bureau.add(flight_agent)
    bureau.add(event_agent)
    
    print("Starting Fetch.ai multi-agent system...")
    print("- Orchestrator Agent: Port 8001")
    print("- Flight Search Agent: Port 8002")
    print("- Event Search Agent: Port 8003")
    print("\nAgents are coordinating via Fetch.ai protocol")
    
    # Run all agents
    bureau.run()