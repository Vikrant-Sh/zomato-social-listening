"""
collection/twitter.py — Module 3B: X/Twitter Collector

════════════════════════════════════════════════════════════════════════════
WHAT THIS MODULE DOES (in plain English)
════════════════════════════════════════════════════════════════════════════

Fetches Zomato-related tweets using Twitter's search API.

HOW IT WORKS:
  1. Call Twitter API v2 search/recent endpoint
  2. Search for "Zomato" tweets
  3. Parse response (JSON)
  4. Normalize fields to standard format
  5. Save to database (with dedupe guard)
  6. Falls back to mock data if API blocked or no credentials

CONFIGURATION:
  Add to .env file:
    TWITTER_BEARER_TOKEN=your_bearer_token
  
  Get token from: https://developer.twitter.com/en/portal/dashboard
════════════════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Dict, List, Tuple
import os

from dotenv import load_dotenv
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import save_post, update_source_status

load_dotenv()


# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
TWITTER_API_TIMEOUT = 10
MAX_TWEETS = 10


# ════════════════════════════════════════════════════════════════════════════
# FETCHING
# ════════════════════════════════════════════════════════════════════════════

def fetch_tweets_from_twitter() -> Tuple[List[Dict], List[str]]:
    """
    Fetch recent tweets mentioning Zomato from Twitter API v2.
    Returns (list of normalized tweets, list of errors).
    Falls back to mock data if blocked or no credentials.
    """
    
    if not TWITTER_BEARER_TOKEN:
        return [], ["No TWITTER_BEARER_TOKEN in .env"]
    
    try:
        url = "https://api.twitter.com/2/tweets/search/recent"
        
        headers = {
            "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
            "User-Agent": "zomato-social-watch/1.0",
        }
        
        params = {
            "query": "Zomato -is:retweet",
            "max_results": MAX_TWEETS,
            "tweet.fields": "created_at,public_metrics,author_id",
            "expansions": "author_id",
            "user.fields": "username",
        }
        
        response = requests.get(
            url, 
            headers=headers, 
            params=params, 
            timeout=TWITTER_API_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        tweets = data.get("data", [])
        includes = data.get("includes", {})
        users_map = {u["id"]: u["username"] for u in includes.get("users", [])}
        
        all_posts = []
        for tweet in tweets:
            normalized = normalize_twitter_post(tweet, users_map)
            all_posts.append(normalized)
        
        return all_posts, []
        
    except requests.exceptions.RequestException as e:
        return [], [f"Twitter API error: {str(e)}"]
    except Exception as e:
        return [], [f"Unexpected error: {str(e)}"]


# ════════════════════════════════════════════════════════════════════════════
# NORMALIZE
# ════════════════════════════════════════════════════════════════════════════

def normalize_twitter_post(tweet: Dict, users_map: Dict) -> Dict:
    """Convert Twitter API response to standard format"""
    
    author_id = tweet.get("author_id")
    author = users_map.get(author_id, "Unknown")
    metrics = tweet.get("public_metrics", {})
    
    posted_at = tweet.get("created_at")
    if posted_at:
        posted_at = datetime.fromisoformat(
            posted_at.replace("Z", "+00:00")
        ).isoformat()
    else:
        posted_at = datetime.now(timezone.utc).isoformat()
    
    normalized = {
        "source": "twitter",
        "source_post_id": tweet.get("id", ""),
        "author": author,
        "title": tweet.get("text", "")[:100],
        "body": tweet.get("text", ""),
        "url": f"https://twitter.com/{author}/status/{tweet.get('id', '')}",
        "posted_at": posted_at,
        "upvotes": metrics.get("retweet_count", 0),
        "comments": metrics.get("reply_count", 0),
    }
    
    return normalized


# ════════════════════════════════════════════════════════════════════════════
# MOCK DATA
# ════════════════════════════════════════════════════════════════════════════

def generate_mock_tweets() -> List[Dict]:
    """Generate mock tweets when API is unavailable"""
    return [
        {
            "source": "twitter",
            "source_post_id": "twitter_mock_1",
            "author": "AngryCustumer92",
            "title": "Just ordered from Zomato, delivery took 3 hours",
            "body": "Ordered biryani, app said 30 min delivery. Came AFTER 3 HOURS. Cold food, support ignored me. Never again.",
            "url": "https://twitter.com/AngryCustumer92/status/mock1",
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "upvotes": 124,
            "comments": 47,
        },
        {
            "source": "twitter",
            "source_post_id": "twitter_mock_2",
            "author": "ZomatoWatch",
            "title": "@ZomatoIn Your service is terrible",
            "body": "5th time this month delivery is late. Support is rude. Why do you keep losing customers? Fix logistics!",
            "url": "https://twitter.com/ZomatoWatch/status/mock2",
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "upvotes": 89,
            "comments": 52,
        },
    ]


# ════════════════════════════════════════════════════════════════════════════
# COLLECT AND SAVE
# ════════════════════════════════════════════════════════════════════════════

def collect_and_save():
    """Fetch tweets, normalize, save to database"""
    
    posts, errors = fetch_tweets_from_twitter()
    used_mock = False
    
    # If Twitter failed, use mock data
    if len(errors) > 0 and len(posts) == 0:
        print("   📌 Twitter blocked/unconfigured, using mock data")
        posts = generate_mock_tweets()
        used_mock = True
        status_msg = "mock"
    else:
        status_msg = "ok" if not errors else f"Partial: {len(posts)}"
    
    new_count = 0
    dup_count = 0
    
    for post in posts:
        is_new = save_post(post)
        if is_new:
            new_count += 1
        else:
            dup_count += 1
    
    update_source_status("twitter", status_msg, len(posts))
    
    return new_count, dup_count, errors, used_mock


# ════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🧪 Module 3B: Twitter Collector")
    print("=" * 70)
    
    new, dups, errors, used_mock = collect_and_save()
    
    print(f"\n✅ Fetch complete:")
    print(f"   New tweets saved: {new}")
    print(f"   Duplicates skipped: {dups}")
    print(f"   Source: {'MOCK DATA' if used_mock else 'LIVE TWITTER'}")
    if errors:
        print(f"   Errors: {errors}")
    
    if new > 0:
        print(f"\n✨ Success! {new} tweets added to database")
