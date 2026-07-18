"""
collectors/reddit.py — Module 3: fetch live Reddit posts mentioning Zomato.

HOW IT WORKS (plain English):
  1. Make a web request to Reddit's public API (no login needed).
  2. Reddit sends back JSON: a list of the newest/hottest posts.
  3. We walk through each post and "normalize" it — rename Reddit's fields
     to match our standard format (source, source_post_id, title, body, etc).
  4. For each post, call save_post() from the database module.
     save_post() says "new post!" or "already have it" (dedupe).
  5. Report back: "fetched 15 posts, saved 12 new ones, 3 were duplicates."

Why public endpoints and not PRAW?
  - Reddit's app approval takes days. Public JSON endpoints work NOW.
  - A subreddit's /hot.json or /new.json is public — no credentials needed.
  - requests (which we already have) is all we need.

What posts do we get?
  - Newest or hottest from subreddits: r/india, r/FoodDelivery, r/zomato, etc.
  - We search the title & body for keywords ("Zomato", "late delivery", etc).
  
If Reddit blocks us, we use mock posts to keep testing the pipeline.
"""

import requests
from datetime import datetime, timezone
from typing import List, Dict, Tuple
import sys
from pathlib import Path

# So this module can import from database/
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import save_post, update_source_status


# ---------------------------------------------------------------- config

REDDIT_SUBREDDITS = [
    "india",
    "FoodDelivery",
    "zomato",
    "indiafood",
]

# These keywords mean a post is probably about Zomato or food delivery problems
KEYWORDS = [
    "zomato",
    "delivery",
    "late",
    "cold food",
    "not delivered",
    "order",
    "missing",
    "refund",
]

REDDIT_API_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------- fetching

def fetch_posts_from_reddit() -> Tuple[List[Dict], List[str]]:
    """
    Fetch the newest posts from our target subreddits.
    Returns (list of normalized posts, list of errors).
    If Reddit is completely blocked, uses mock data instead.
    """
    all_posts = []
    errors = []

    for subreddit in REDDIT_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            params = {"limit": 50}  # fetch 50 posts per subreddit

            response = requests.get(
                url, headers=headers, params=params, timeout=REDDIT_API_TIMEOUT
            )
            response.raise_for_status()  # raise an error if 404 or 500

            data = response.json()
            posts = data.get("data", {}).get("children", [])

            for post_wrapper in posts:
                post = post_wrapper.get("data", {})
                normalized = normalize_reddit_post(post)
                if normalized:
                    all_posts.append(normalized)

        except requests.exceptions.RequestException as e:
            errors.append(f"{subreddit}: {str(e)}")
        except Exception as e:
            errors.append(f"{subreddit}: unexpected error {type(e).__name__}")

    return all_posts, errors


# ---------------------------------------------------------------- normalize

def normalize_reddit_post(reddit_post: Dict) -> Dict:
    """
    Convert a Reddit post's fields into our standard format.

    Reddit gives us: id, title, selftext, author, ups, num_comments, url, created_utc
    We want:         source, source_post_id, title, body, author, upvotes, comments, url, posted_at

    Also: only return posts that mention Zomato or delivery issues.
    """
    title = reddit_post.get("title", "").lower()
    body = reddit_post.get("selftext", "").lower()
    combined_text = f"{title} {body}"

    # Only keep posts that match our keywords
    if not any(keyword in combined_text for keyword in KEYWORDS):
        return None  # skip this post, not relevant

    # Convert Reddit's Unix timestamp to ISO format
    created_utc = reddit_post.get("created_utc")
    if created_utc:
        posted_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()
    else:
        posted_at = datetime.now(timezone.utc).isoformat()

    normalized = {
        "source": "reddit",
        "source_post_id": reddit_post.get("id", ""),
        "author": reddit_post.get("author", "Unknown"),
        "title": reddit_post.get("title", ""),
        "body": reddit_post.get("selftext", ""),
        "url": f"https://reddit.com{reddit_post.get('permalink', '')}",
        "posted_at": posted_at,
        "upvotes": reddit_post.get("ups", 0),
        "comments": reddit_post.get("num_comments", 0),
    }

    return normalized


# ---------------------------------------------------------------- mock data (fallback for when Reddit is blocked)

def generate_mock_posts() -> List[Dict]:
    """
    Generate realistic fake Reddit posts for testing when the API is blocked.
    This lets you test the entire pipeline without waiting for Reddit access.
    """
    mock_posts = [
        {
            "source": "reddit",
            "source_post_id": "mock1",
            "author": "FoodieRohit",
            "title": "Zomato delivery took 2 hours for a 5km distance - unacceptable!",
            "body": "I ordered biryani from a restaurant 5km away. Expected delivery was 30-40 mins. It came AFTER 2 HOURS. The food was cold. Called customer support, they were rude. No refund offered.",
            "url": "https://reddit.com/r/india/mock1",
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "upvotes": 47,
            "comments": 23,
        },
        {
            "source": "reddit",
            "source_post_id": "mock2",
            "author": "DeliveryComplains",
            "title": "Order never delivered - Zomato refund rejected",
            "body": "Placed order for lunch, paid 850 rupees. Delivery partner said 'out for delivery' for 1.5 hours, then order was cancelled. Zomato refused to refund. This is scam.",
            "url": "https://reddit.com/r/FoodDelivery/mock2",
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "upvotes": 62,
            "comments": 31,
        },
        {
            "source": "reddit",
            "source_post_id": "mock3",
            "author": "MumbaiUser",
            "title": "Cold food delivered - is this normal for Zomato?",
            "body": "Third time this month. Order placed, says 25 min delivery, takes 60 mins, arrives ice cold. What's going on? Other apps deliver hot food on time.",
            "url": "https://reddit.com/r/zomato/mock3",
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "upvotes": 38,
            "comments": 18,
        },
        {
            "source": "reddit",
            "source_post_id": "mock4",
            "author": "IndianTech",
            "title": "Why I deleted Zomato - latest delivery experience was the last straw",
            "body": "Consistent issues: late delivery, cold food, missing items. Support tickets go nowhere. Switched to Swiggy, much better experience. Zomato needs to fix their logistics.",
            "url": "https://reddit.com/r/indiafood/mock4",
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "upvotes": 91,
            "comments": 44,
        },
        {
            "source": "reddit",
            "source_post_id": "mock5",
            "author": "CustomerServiceIssue",
            "title": "Zomato customer service is non-existent",
            "body": "Had a problem with my order (item was wrong). Called support 10 times over 3 days. No one picked up. Sent emails, no response for 5 days. This is ridiculous for a big company.",
            "url": "https://reddit.com/r/india/mock5",
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "upvotes": 73,
            "comments": 52,
        },
    ]
    return mock_posts


# ---------------------------------------------------------------- save all

def collect_and_save():
    """
    Fetch posts from Reddit, normalize, and save to database.
    If Reddit is completely blocked, use mock data.
    Returns (num_new, num_duplicates, errors, used_mock).
    """
    posts, errors = fetch_posts_from_reddit()
    used_mock = False

    # If Reddit failed completely, use mock data
    if len(errors) == len(REDDIT_SUBREDDITS) and len(posts) == 0:
        print("   ⚠️  Reddit blocked. Using mock data to test the pipeline...\n")
        posts = generate_mock_posts()
        used_mock = True
        status_msg = "mock"
    else:
        if errors:
            status_msg = f"Partial: {len(posts)} posts, {len(errors)} error(s)"
        else:
            status_msg = "ok"

    new_count = 0
    dup_count = 0

    for post in posts:
        is_new = save_post(post)
        if is_new:
            new_count += 1
        else:
            dup_count += 1

    # Report status to database
    update_source_status("reddit", status_msg, len(posts))

    return new_count, dup_count, errors, used_mock


# ---------------------------------------------------------------- self-test

if __name__ == "__main__":
    print("🔍 Module 3 self-test: fetching live Reddit posts...")
    print(f"   Subreddits: {', '.join(REDDIT_SUBREDDITS)}")
    print(f"   Keywords: {', '.join(KEYWORDS)}")
    print(f"   (If Reddit is blocked, mock posts will be used for testing)\n")

    new, dups, errors, used_mock = collect_and_save()

    print(f"\n✅ Fetch complete:")
    print(f"   New posts saved: {new}")
    print(f"   Duplicates skipped: {dups}")
    if used_mock:
        print(f"   Source: MOCK DATA (Reddit was blocked)")
    else:
        print(f"   Source: LIVE REDDIT")
    if errors:
        print(f"   Errors: {len(errors)}")
        for e in errors:
            print(f"     - {e}")
    else:
        print(f"   Errors: none")

    if new > 0:
        print(f"\n✨ Success! Check the database to see your posts.")
    elif dups > 0:
        print(f"\n✨ All posts were already in the database (dedupe working).")
    else:
        print(f"\n⚠️  No posts found.")
