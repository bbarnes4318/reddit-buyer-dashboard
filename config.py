import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Reddit API configuration
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")

# Gemini API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBX_4_GoOitrlS30Fa-wVscPkuovZ6bdN4")

# Application settings
MONITORING_INTERVAL_MINUTES = int(os.getenv("MONITORING_INTERVAL_MINUTES", "30"))
MAX_POSTS_PER_SUBREDDIT = int(os.getenv("MAX_POSTS_PER_SUBREDDIT", "25"))
DM_COOLDOWN_HOURS = int(os.getenv("DM_COOLDOWN_HOURS", "24"))

# Subreddits and keywords to monitor
# These can be expanded or loaded from a database
MONITORED_SUBREDDITS = [
    "buildapc",
    "gadgets",
    "homeautomation",
    "software",
    "technology",
    "marketing",
    "productivity",
    "smallbusiness",
    "startups",
    "entrepreneur"
]

# Keywords to look for in posts and comments
BUYER_INTENT_KEYWORDS = [
    "recommend",
    "looking for",
    "best",
    "alternative to",
    "vs",
    "compare",
    "should I buy",
    "worth it",
    "experience with",
    "thinking about getting",
    "need advice",
    "purchase",
    "buying",
    "suggest"
]

# Intent classifications
INTENT_CATEGORIES = {
    "HIGH": "High Buyer Intent",
    "MEDIUM": "Medium Buyer Intent",
    "LOW": "Low Buyer Intent",
    "NONE": "No Buyer Intent"
}

# API rate limits (to comply with Reddit's policies)
API_RATE_LIMIT_SECONDS = 2  # Minimum seconds between API requests 