import os
from dotenv import load_dotenv

load_dotenv()

# AI Core APIs
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Data & APIs
BRIGHT_DATA_API_KEY = os.getenv("BRIGHT_DATA_API_KEY")
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
ELASTIC_CLOUD_ID = os.getenv("ELASTIC_CLOUD_ID")
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")

# Fetch.ai Agent Configuration
AGENT_SEED = os.getenv("AGENT_SEED", "default_seed_phrase_change_this")
AGENT_MAILBOX_KEY = os.getenv("AGENT_MAILBOX_KEY")
AGENT_PORT = 8001

# Model Configuration
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
GROQ_MODEL = "llama-3.3-70b-versatile"  # Fast for real-time responses