"""
config.py — the single settings notebook for Social Watch.

Every other file asks THIS file for numbers, names, and secrets.
Change a threshold here, and the whole system obeys.

Secrets come from the .env file (loaded below).
Everything else is a plain constant you can read and tune.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ------------------------------------------------------------------
# 1. Load the secret pocket (.env) into environment variables
# ------------------------------------------------------------------
# Path(__file__).parent = the project folder, wherever it lives.
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")

# ------------------------------------------------------------------
# 2. Secrets (read from .env — never hardcoded here)
# ------------------------------------------------------------------
# Reddit: public JSON endpoints — no keys needed, just a polite user agent
REDDIT_USER_AGENT = os.getenv(
    "REDDIT_USER_AGENT", "social-watch (personal assignment demo)"
)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_TOKEN", "")
CLICKUP_LIST_ID = os.getenv("CLICKUP_LIST_ID", "")

# ------------------------------------------------------------------
# 3. Database
# ------------------------------------------------------------------
DB_PATH = str(PROJECT_ROOT / "database" / "socialwatch.db")

# ------------------------------------------------------------------
# 4. What to search for, and where
# ------------------------------------------------------------------
SEARCH_KEYWORD = "zomato"

# Subreddits worth watching (high India + food + city coverage)
SUBREDDITS = [
    "india",
    "indianfood",
    "bangalore",
    "delhi",
    "mumbai",
    "developersIndia",
]

# Google News RSS feed for Zomato (feedparser will read this URL)
NEWS_RSS_URL = (
    "https://news.google.com/rss/search?q=zomato&hl=en-IN&gl=IN&ceid=IN:en"
)

# How many posts to pull per source per cycle (keeps cycles fast & cheap)
MAX_POSTS_PER_SOURCE = 25

# ------------------------------------------------------------------
# 5. The 6 categories (must match the classifier prompt EXACTLY)
# ------------------------------------------------------------------
CATEGORIES = [
    "Safety Incident",        # food safety OR rider safety — worst class
    "Viral Complaint",        # PR risk: negative + gaining traction
    "Service Outage",         # app down / payments stuck / orders failing
    "Fraud Scam",             # fake Zomato calls, refund scams
    "Routine Complaint",      # single cold-food / late-order gripe
    "Noise",                  # everything else that slipped through
]

# Categories that ALWAYS escalate, no matter how small (the "floor")
FLOOR_CATEGORIES = ["Safety Incident", "Fraud Scam"]
FLOOR_SCORE = 70  # floor categories get at least this score

# ------------------------------------------------------------------
# 6. Scoring rules  (score = severity + engagement + recency, max 100)
# ------------------------------------------------------------------
SEVERITY_MAX_POINTS = 50     # Claude's 1–5 judgment, scaled to 0–50
ENGAGEMENT_MAX_POINTS = 30   # log-scaled likes/upvotes, capped at 30
RECENCY_MAX_POINTS = 20      # fresher post = more points, capped at 20
RECENCY_WINDOW_HOURS = 2     # posts older than this get 0 recency points

ESCALATE_THRESHOLD = 70      # score >= 70  -> ESCALATE (actions fire)
WATCH_THRESHOLD = 40         # score 40–69  -> WATCH (visible, no action)
                             # score < 40   -> LOG (stored quietly)

# Outage cluster rule: this many Service Outage posts in ONE cycle
# = treat it as one big outage escalation
OUTAGE_CLUSTER_MIN = 5

# ------------------------------------------------------------------
# 7. Claude settings
# ------------------------------------------------------------------
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_BATCH_SIZE = 15       # posts per API call (cheaper than one-by-one)
CLAUDE_MAX_TOKENS = 2000

# ------------------------------------------------------------------
# 8. Scheduler
# ------------------------------------------------------------------
REFRESH_MINUTES = 5          # the assignment's "at least every 5 minutes"


def check_secrets() -> list[str]:
    """
    Return a list of secret names that are still EMPTY.

    Used at startup to warn you nicely ("hey, you forgot the Slack URL")
    instead of crashing mysteriously mid-pipeline.
    """
    required = {
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "SLACK_WEBHOOK_URL": SLACK_WEBHOOK_URL,
        "CLICKUP_API_TOKEN": CLICKUP_API_TOKEN,
        "CLICKUP_LIST_ID": CLICKUP_LIST_ID,
    }
    return [name for name, value in required.items() if not value]


if __name__ == "__main__":
    # Tiny self-test: run `python config.py` to see what's missing.
    missing = check_secrets()
    if missing:
        print("⚠️  Missing secrets in .env:", ", ".join(missing))
    else:
        print("✅ All secrets loaded.")
    print(f"✅ Database will live at: {DB_PATH}")
    print(f"✅ Watching {len(SUBREDDITS)} subreddits for '{SEARCH_KEYWORD}'")
