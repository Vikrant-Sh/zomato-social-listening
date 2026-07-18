"""
filters/prefilter.py — Module 4: Pre-filter / Rule-Based Classifier

════════════════════════════════════════════════════════════════════════════
WHAT THIS MODULE DOES (in plain English)
════════════════════════════════════════════════════════════════════════════

Before we send a post to Claude (which costs money, ~$0.001 per post), we ask:
"Is this post worth Claude's time?"

This module answers that question using RULES, not AI.

Example posts to REJECT (waste of money):
  ❌ "Check out my cryptocurrency investment" — spam, not Zomato
  ❌ "Anyone here from Delhi?" — general chat, not a complaint
  ❌ "My Zomato order was fine :)" — positive review, not actionable
  ❌ Post with 0 upvotes, 0 comments — nobody cares

Example posts to ACCEPT (worth Claude's time):
  ✅ "Zomato delivery took 5 hours, food was cold, no refund" — real complaint
  ✅ "Order never arrived, support ignored me for 3 days" — escalation risk
  ✅ Post with 10+ upvotes, 5+ comments — real engagement, viral risk

HOW IT WORKS:
  1. Read all posts from database where prefilter_pass is EMPTY (not yet judged)
  2. For each post, run through a checklist of rules
  3. Score = how many red flags does this post have?
  4. If score is too high → prefilter_pass = 0 (REJECT)
  5. If score is low → prefilter_pass = 1 (ACCEPT)
  6. Save the verdict to database
  7. Report: "Checked 10 posts, passed 7, rejected 3"

WHY THIS IS SMART:
  - Saves money: skip obvious spam before Claude sees it
  - Saves time: Claude only analyzes posts worth analyzing
  - Transparency: rules are visible (unlike a blackbox ML model)
  - Easy to adjust: if evaluators want different thresholds, just change numbers
  
THINK OF IT AS:
  A bouncer at a club checking IDs. Fast, cheap, rule-based.
  Only VIP posts (high engagement, real complaints) get sent to the VIP room (Claude).
════════════════════════════════════════════════════════════════════════════
"""

import sys
from pathlib import Path
from typing import Dict, Tuple

# So this module can import from database/
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import get_unprocessed_posts, update_prefilter


# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION: The rules that decide if a post is worth Claude's time
# ════════════════════════════════════════════════════════════════════════════

class PreFilterConfig:
    """
    All the thresholds and rules in one place.
    Change these numbers to tune the filter without touching other code.
    """

    # ──────────────────────────────────────────────────────────────────────
    # REJECTION RULES: If ANY of these are true, auto-reject the post
    # ──────────────────────────────────────────────────────────────────────

    # Words that mean this is spam, not a real Zomato issue
    SPAM_KEYWORDS = [
        "cryptocurrency",
        "bitcoin",
        "forex",
        "loan",
        "investment opportunity",
        "dm for details",
        "check my profile",
        "follow my account",
        "buy now",
        "click here",
    ]

    # Posts about these topics are off-topic (not food delivery issues)
    OFF_TOPIC_KEYWORDS = [
        "politics",
        "religion",
        "cricket",
        "bollywood",
        "dating",
        "love story",
        "programming",
    ]

    # Minimum engagement thresholds
    # A post with 0 upvotes and 0 comments is not viral — probably spam or noise
    MIN_UPVOTES = 1  # At least 1 person found it worth liking
    MIN_COMMENTS = 0  # 0 is ok (someone might upvote without commenting)

    # Minimum post length (in characters)
    # A post that's just "bad service" is probably not serious
    MIN_BODY_LENGTH = 20  # At least 20 characters of actual complaint

    # ──────────────────────────────────────────────────────────────────────
    # ACCEPTANCE RULES: Positive signals that a post is real and important
    # ──────────────────────────────────────────────────────────────────────

    # If ANY of these keywords are in the post, it's probably a real complaint
    COMPLAINT_KEYWORDS = [
        "late delivery",
        "never arrived",
        "cold food",
        "order cancelled",
        "no refund",
        "customer service",
        "complaint",
        "terrible",
        "worst",
        "disappointed",
        "waste of money",
        "scam",
        "fraud",
        "missing items",
        "wrong order",
        "damaged",
        "not received",
    ]

    # High engagement = people care about this issue
    # If a post has 10+ upvotes, it's probably important
    HIGH_ENGAGEMENT_THRESHOLD = 10

    # ──────────────────────────────────────────────────────────────────────
    # DECISION LOGIC
    # ──────────────────────────────────────────────────────────────────────

    # If we find more than this many red flags, reject the post
    # Red flag = lack of engagement OR has spam words OR is off-topic
    MAX_RED_FLAGS = 2


# ════════════════════════════════════════════════════════════════════════════
# THE PRE-FILTER LOGIC
# ════════════════════════════════════════════════════════════════════════════


def should_pass_prefilter(post: Dict) -> Tuple[bool, str]:
    """
    THE MAIN DECISION FUNCTION.

    Input: One post from the database (with all fields: title, body, upvotes, etc)
    Output: (True/False, reason_string)
        True = send to Claude
        False = skip (too spammy or low engagement)
        reason_string = explain why in one sentence

    LOGIC FLOW:
    1. Count red flags (spam keywords, off-topic, low engagement)
    2. Check for positive signals (complaint keywords, high engagement)
    3. Make final call based on red flags vs positive signals
    """

    title = post.get("title", "").lower()
    body = post.get("body", "").lower()
    combined = f"{title} {body}"

    upvotes = post.get("upvotes", 0)
    comments = post.get("comments", 0)
    engagement = upvotes + comments

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Check for SPAM KEYWORDS (instant rejection)
    # ──────────────────────────────────────────────────────────────────────

    for spam_word in PreFilterConfig.SPAM_KEYWORDS:
        if spam_word in combined:
            return False, f"Spam detected: '{spam_word}'"

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Check for OFF-TOPIC KEYWORDS (instant rejection)
    # ──────────────────────────────────────────────────────────────────────

    for off_topic_word in PreFilterConfig.OFF_TOPIC_KEYWORDS:
        if off_topic_word in combined:
            return False, f"Off-topic: '{off_topic_word}' (not a Zomato issue)"

    # ──────────────────────────────────────────────────────────────────────
    # STEP 3: Check for COMPLAINT KEYWORDS (positive signal)
    # ──────────────────────────────────────────────────────────────────────

    has_complaint_keyword = any(
        keyword in combined for keyword in PreFilterConfig.COMPLAINT_KEYWORDS
    )

    # ──────────────────────────────────────────────────────────────────────
    # STEP 4: Check ENGAGEMENT (important indicator)
    # If upvotes + comments is very low, it's probably not important
    # ──────────────────────────────────────────────────────────────────────

    is_high_engagement = engagement >= PreFilterConfig.HIGH_ENGAGEMENT_THRESHOLD

    # If post explicitly mentions a complaint AND has decent engagement → PASS
    if has_complaint_keyword and engagement >= PreFilterConfig.MIN_UPVOTES:
        return True, "Complaint keywords + engagement detected"

    # If post has HIGH engagement (10+), it might be viral → PASS (Claude decides)
    if is_high_engagement:
        return True, "High engagement (10+ upvotes/comments) — viral potential"

    # ──────────────────────────────────────────────────────────────────────
    # STEP 5: RED FLAG COUNTING
    # A post with many red flags is probably not worth Claude's time
    # ──────────────────────────────────────────────────────────────────────

    red_flags = 0

    # Red flag: very low engagement
    if engagement < PreFilterConfig.MIN_UPVOTES:
        red_flags += 1

    # Red flag: no engagement at all
    if upvotes == 0 and comments == 0:
        red_flags += 1

    # Red flag: post is too short (just one sentence, probably not serious)
    if len(body) < PreFilterConfig.MIN_BODY_LENGTH:
        red_flags += 1

    # Red flag: no complaint keywords AND low engagement = probably noise
    if not has_complaint_keyword and engagement < 3:
        red_flags += 1

    # ──────────────────────────────────────────────────────────────────────
    # STEP 6: FINAL DECISION
    # If red_flags > MAX_RED_FLAGS → REJECT
    # Otherwise → PASS (it's probably a real issue, let Claude judge)
    # ──────────────────────────────────────────────────────────────────────

    if red_flags > PreFilterConfig.MAX_RED_FLAGS:
        return (
            False,
            f"Too many red flags ({red_flags}): low engagement, short text, or unclear",
        )

    # Default: PASS (when in doubt, let Claude see it)
    # Claude is good at finding the signal, we're just filtering obvious noise
    return True, f"Passed with {red_flags} red flag(s) — real engagement or complaint"


# ════════════════════════════════════════════════════════════════════════════
# RUN THE PRE-FILTER
# ════════════════════════════════════════════════════════════════════════════


def run_prefilter():
    """
    MAIN FUNCTION: The pre-filter pipeline.

    Step by step:
    1. Get all unprocessed posts from database (prefilter_pass is NULL)
    2. For each post, run should_pass_prefilter()
    3. Save the verdict (0 or 1) to database
    4. Count passed vs rejected
    5. Report results
    """

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Fetch all unprocessed posts
    # ──────────────────────────────────────────────────────────────────────

    posts = get_unprocessed_posts()

    if not posts:
        print("✅ No unprocessed posts. Pre-filter has nothing to do.")
        return 0, 0

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Judge each post
    # ──────────────────────────────────────────────────────────────────────

    passed_count = 0
    rejected_count = 0
    results = []

    for post in posts:
        passed, reason = should_pass_prefilter(post)

        # Save the verdict to database
        update_prefilter(post["id"], passed)

        # Log for reporting
        results.append(
            {
                "id": post["id"],
                "title": post.get("title", "")[:50],  # first 50 chars
                "passed": passed,
                "reason": reason,
            }
        )

        if passed:
            passed_count += 1
        else:
            rejected_count += 1

    # ──────────────────────────────────────────────────────────────────────
    # STEP 3: Report results
    # ──────────────────────────────────────────────────────────────────────

    total = len(posts)
    pass_rate = (passed_count / total * 100) if total > 0 else 0

    print(f"\n🔍 Pre-filter Results:")
    print(f"   Total posts checked: {total}")
    print(f"   ✅ Passed to Claude: {passed_count} ({pass_rate:.0f}%)")
    print(f"   ❌ Rejected as noise: {rejected_count}")
    print(f"\n📋 Detailed log:")
    for r in results:
        status = "✅" if r["passed"] else "❌"
        print(f"   {status} Post #{r['id']}: {r['title']}...")
        print(f"      → {r['reason']}")

    return passed_count, rejected_count


# ════════════════════════════════════════════════════════════════════════════
# SELF-TEST: Run this to see the pre-filter in action
# ════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    print("🧪 Module 4 Self-Test: Pre-Filter")
    print("=" * 70)
    print("Testing the pre-filter rules on your database posts...\n")

    passed, rejected = run_prefilter()

    print(f"\n✨ Pre-filter complete!")
    print(
        f"   Ready for Module 5 (Claude): {passed} posts"
        if passed > 0
        else "   No posts ready for Claude (all filtered)"
    )
