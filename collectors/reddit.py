"""
collectors/reddit.py — Module 3: fetch recent posts from r/zomato.

HOW IT WORKS (plain English):
  1. Download the subreddit's public RSS feed (no login needed).
  2. Parse the feed and keep its ten newest entries.
  3. We walk through each entry and "normalize" it — rename RSS fields
     to match our standard format (source, source_post_id, title, body, etc).
  4. For each post, call save_post() from the database module.
     save_post() says "new post!" or "already have it" (dedupe).
  5. Report how many posts were new and how many were duplicates.

Why RSS and not PRAW?
  - The public RSS feed does not require Reddit API credentials.
  - The project already depends on feedparser.
  - Ten scheduled runs spread through a day stay below the observed RSS limit.

What posts do we get?
  - The ten newest entries from r/zomato.
  - RSS does not include upvote or comment counts, so those values are zero.

If Reddit blocks us, we use mock posts to keep testing the pipeline.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Dict, List, Tuple

import feedparser
import requests

# So this module can import from database/
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import save_post, update_source_status


# ---------------------------------------------------------------- config

REDDIT_SUBREDDITS = [
    "zomato",
]

REDDIT_API_TIMEOUT = 10  # seconds
MAX_POSTS_PER_SUBREDDIT = 10
REDDIT_USER_AGENT = "macos:zomato-social-watch:v1.0.0 (RSS collector)"


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
            url = f"https://www.reddit.com/r/{subreddit}/new/.rss"
            response = requests.get(
                url,
                headers={"User-Agent": REDDIT_USER_AGENT},
                timeout=REDDIT_API_TIMEOUT,
            )
            response.raise_for_status()

            feed = feedparser.parse(response.content)
            if feed.bozo and not feed.entries:
                raise ValueError(f"invalid RSS feed: {feed.bozo_exception}")

            for entry in feed.entries[:MAX_POSTS_PER_SUBREDDIT]:
                all_posts.append(normalize_reddit_post(entry))

        except requests.exceptions.RequestException as e:
            errors.append(f"{subreddit}: {str(e)}")
        except (TypeError, ValueError) as e:
            errors.append(f"{subreddit}: {str(e)}")

    return all_posts, errors


# ---------------------------------------------------------------- normalize

def normalize_reddit_post(reddit_post: Dict) -> Dict:
    """
    Convert a Reddit post's fields into our standard format.

    RSS gives us:    id, title, summary, author, link, published_parsed
    We want:         source, source_post_id, title, body, author, upvotes, comments, url, posted_at
    """
    published = reddit_post.get("published_parsed")
    if published:
        posted_at = datetime(*published[:6], tzinfo=timezone.utc).isoformat()
    else:
        posted_at = datetime.now(timezone.utc).isoformat()

    normalized = {
        "source": "reddit",
        "source_post_id": reddit_post.get("id", reddit_post.get("link", "")),
        "author": reddit_post.get("author", "Unknown"),
        "title": reddit_post.get("title", ""),
        "body": reddit_post.get("summary", ""),
        "url": reddit_post.get("link", ""),
        "posted_at": posted_at,
        "upvotes": 0,
        "comments": 0,
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
    print("🔍 Module 3 self-test: fetching live Reddit RSS posts...")
    print(f"   Subreddits: {', '.join(REDDIT_SUBREDDITS)}")
    print(f"   Latest posts per subreddit: {MAX_POSTS_PER_SUBREDDIT}")
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
