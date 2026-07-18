"""
collection/rss.py — Module 3C: RSS Feed Collector

════════════════════════════════════════════════════════════════════════════
WHAT THIS MODULE DOES (in plain English)
════════════════════════════════════════════════════════════════════════════

Fetches Zomato mentions from RSS feeds (news, blogs, forums).

HOW IT WORKS:
  1. Subscribe to RSS feeds about food delivery and restaurants
  2. Fetch and parse each feed (using feedparser)
  3. Filter entries by Zomato keywords
  4. Normalize to standard format
  5. Save to database (with dedupe guard)
  6. Falls back to mock data if feeds blocked

CONFIGURED FEEDS (add your own):
  - Tech news (Zomato funding, acquisitions)
  - Restaurant review sites (Zomato ratings)
  - Food delivery blogs
  - News aggregators

Example: https://www.reddit.com/r/zomato/new/.rss (Reddit RSS)
════════════════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Dict, List, Tuple

import feedparser

sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import save_post, update_source_status


# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION: RSS Feeds to monitor
# ════════════════════════════════════════════════════════════════════════════

# Add real RSS feed URLs here
RSS_FEEDS = [
    # Reddit RSS feeds about food delivery
    "https://www.reddit.com/r/Zomato/new/.rss",
    "https://www.reddit.com/r/FoodDelivery/new/.rss",
    # Add more feeds as needed:
    # "https://feeds.techcrunch.com/",
    # "https://www.producthunt.com/feed",
]

KEYWORDS = [
    "zomato",
    "delivery",
    "food",
    "restaurant",
    "late",
    "order",
    "refund",
]

MAX_ENTRIES_PER_FEED = 10
RSS_TIMEOUT = 10


# ════════════════════════════════════════════════════════════════════════════
# FETCHING
# ════════════════════════════════════════════════════════════════════════════

def fetch_rss_entries() -> Tuple[List[Dict], List[str]]:
    """
    Fetch entries from RSS feeds.
    Returns (list of normalized entries, list of errors).
    """
    all_entries = []
    errors = []
    
    for feed_url in RSS_FEEDS:
        try:
            # Parse the RSS feed
            feed = feedparser.parse(feed_url)
            
            # Check for errors
            if feed.bozo and not feed.entries:
                errors.append(f"{feed_url}: Invalid RSS feed")
                continue
            
            # Extract entries
            for entry in feed.entries[:MAX_ENTRIES_PER_FEED]:
                normalized = normalize_rss_entry(entry)
                if normalized:  # Only keep if it has Zomato keywords
                    all_entries.append(normalized)
                    
        except Exception as e:
            errors.append(f"{feed_url}: {str(e)}")
    
    return all_entries, errors


# ════════════════════════════════════════════════════════════════════════════
# NORMALIZE
# ════════════════════════════════════════════════════════════════════════════

def normalize_rss_entry(entry: Dict) -> Dict:
    """
    Convert RSS entry to standard format.
    RSS feeds have: title, summary, link, published, author
    We want: title, body, author, upvotes, comments, posted_at, url
    """
    
    title = entry.get("title", "")
    summary = entry.get("summary", "")
    combined = f"{title} {summary}".lower()
    
    # Filter by keywords (only keep Zomato-related)
    if not any(keyword in combined for keyword in KEYWORDS):
        return None  # Not relevant
    
    # Parse publish date
    published = entry.get("published_parsed")
    if published:
        posted_at = datetime(*published[:6], tzinfo=timezone.utc).isoformat()
    else:
        posted_at = datetime.now(timezone.utc).isoformat()
    
    normalized = {
        "source": "rss",
        "source_post_id": entry.get("id", entry.get("link", "")),
        "author": entry.get("author", "Unknown"),
        "title": title,
        "body": summary,
        "url": entry.get("link", ""),
        "posted_at": posted_at,
        "upvotes": 0,  # RSS doesn't have engagement metrics
        "comments": 0,
    }
    
    return normalized


# ════════════════════════════════════════════════════════════════════════════
# MOCK DATA
# ════════════════════════════════════════════════════════════════════════════

def generate_mock_rss_entries() -> List[Dict]:
    """Generate mock RSS entries when feeds are unavailable"""
    return [
        {
            "source": "rss",
            "source_post_id": "rss_mock_1",
            "author": "TechCrunch News",
            "title": "Zomato faces major outage, thousands unable to place orders",
            "body": "Multiple users reported Zomato app crashes during peak dinner hours. Systems down for 2 hours, affecting thousands of orders. Company promises compensation.",
            "url": "https://techcrunch.example.com/zomato-outage",
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "upvotes": 0,
            "comments": 0,
        },
        {
            "source": "rss",
            "source_post_id": "rss_mock_2",
            "author": "Food Delivery Blog",
            "title": "Zomato delivery delays surge 40% in monsoon season",
            "body": "Analysis shows Zomato experiencing significant delays. Avg delivery time increased 30 min to 42 min. Multiple customer complaints. Company blames weather.",
            "url": "https://fooddeliveryblog.example.com/zomato-delays",
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "upvotes": 0,
            "comments": 0,
        },
    ]


# ════════════════════════════════════════════════════════════════════════════
# COLLECT AND SAVE
# ════════════════════════════════════════════════════════════════════════════

def collect_and_save():
    """Fetch RSS entries, normalize, save to database"""
    
    entries, errors = fetch_rss_entries()
    used_mock = False
    
    # If RSS failed completely, use mock data
    if len(errors) == len(RSS_FEEDS) and len(entries) == 0:
        print("   📌 RSS feeds blocked/unavailable, using mock data")
        entries = generate_mock_rss_entries()
        used_mock = True
        status_msg = "mock"
    else:
        status_msg = "ok" if not errors else f"Partial: {len(entries)}"
    
    new_count = 0
    dup_count = 0
    
    for entry in entries:
        is_new = save_post(entry)
        if is_new:
            new_count += 1
        else:
            dup_count += 1
    
    update_source_status("rss", status_msg, len(entries))
    
    return new_count, dup_count, errors, used_mock


# ════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🧪 Module 3C: RSS Collector")
    print("=" * 70)
    print(f"   Feeds configured: {len(RSS_FEEDS)}\n")
    
    new, dups, errors, used_mock = collect_and_save()
    
    print(f"\n✅ Fetch complete:")
    print(f"   New entries saved: {new}")
    print(f"   Duplicates skipped: {dups}")
    print(f"   Source: {'MOCK DATA' if used_mock else 'LIVE FEEDS'}")
    if errors:
        for e in errors:
            print(f"   - {e}")
    
    if new > 0:
        print(f"\n✨ Success! {new} RSS entries added to database")
