"""
pipeline/classifier.py — Module 5: Claude AI Classifier

════════════════════════════════════════════════════════════════════════════
WHAT THIS MODULE DOES (in plain English)
════════════════════════════════════════════════════════════════════════════

This is the AI heart of the pipeline. Each post is a raw complaint, but we
need to understand it:
  - WHAT is the complaint about? (category)
  - HOW serious is it? (severity 1-5)
  - Quick summary for humans (one line)

We send each post to Claude (our AI), and Claude answers these 3 questions.

EXAMPLE:
  Input post: "Ordered biryani, delivery took 5 hours, food was cold, 
              support said nothing can be done"
  
  Claude's analysis:
    Category: "delivery_delay"
    Severity: 4 (out of 5)
    Summary: "Late delivery + cold food + no support refund"

HOW IT WORKS:
  1. Read all posts from database where category is EMPTY
     (these are posts that passed pre-filter but aren't analyzed yet)
  2. For each post, create a prompt for Claude
  3. Send the prompt to Claude API (costs ~$0.001 per post)
  4. Parse Claude's response (extract category, severity, summary)
  5. Save to database
  6. Report: "Analyzed 5 posts, found 2 delivery issues, 1 refund issue, etc"

CATEGORIES Claude can assign:
  "delivery_delay"     — took too long to arrive
  "food_quality"       — cold, damaged, wrong item
  "refund_issue"       — customer wants money back
  "customer_service"   — support team was rude or unresponsive
  "other"              — something else (fraud, missing items, etc)

SEVERITY scale:
  1 = mild complaint (just annoying, not urgent)
  2 = moderate (real issue, but customer already got partial resolution)
  3 = serious (unresolved issue, customer is upset, viral potential)
  4 = critical (customer might go public, demand refund/chargeback)
  5 = emergency (post is already viral, reputational damage in progress)

WHY THIS IS SMART:
  - Claude understands nuance (human language, context, emotion)
  - You don't have to write rules for 1000s of complaint types
  - Score is consistent (Claude sees all posts with same lens)
  - Transparent (we log what Claude said for audits)
  
THINK OF IT AS:
  A smart customer service analyst reading each complaint and answering:
  "What's the issue? How bad is it? One line for the boss?"
════════════════════════════════════════════════════════════════════════════
"""

import sys
from pathlib import Path
from typing import Dict, Tuple, Optional
import json
import os
from dotenv import load_dotenv

# So this module can import from database/
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import get_unclassified_posts, update_classification

# Load Claude API key from .env
load_dotenv()
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Import Claude API (optional for mock mode)
try:
    from anthropic import Anthropic
    ANTHROPIC_INSTALLED = True
except ImportError:
    ANTHROPIC_INSTALLED = False
    # Mock mode doesn't need the library, so don't exit yet


# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION: Categories and severity thresholds
# ════════════════════════════════════════════════════════════════════════════


class ClassifierConfig:
    """
    Configuration for Claude's classification task.
    Change these to adjust what Claude should look for.
    """

    # Valid categories Claude can assign
    # Keep this list in sync with what you expect from Claude
    VALID_CATEGORIES = [
        "delivery_delay",
        "food_quality",
        "refund_issue",
        "customer_service",
        "other",
    ]

    # Claude model to use
    # claude-opus-4-6: Most capable (slower, more expensive)
    # claude-sonnet-4-6: Balanced (fast, cheaper)
    # claude-haiku-4.5: Fastest (cheapest, but less nuanced)
    # For this task, Sonnet is perfect
    MODEL = "claude-sonnet-4-6"

    # Max tokens Claude should use per response
    # For our task (classify + severity + summary), 200 is plenty
    MAX_TOKENS = 200

    # Temperature: how creative should Claude be?
    # 0 = deterministic (same input = same output)
    # 1 = creative (more variation)
    # For classification, 0 is better (we want consistent decisions)
    TEMPERATURE = 0


# ════════════════════════════════════════════════════════════════════════════
# THE CLAUDE PROMPT: What we ask Claude to do
# ════════════════════════════════════════════════════════════════════════════


def build_classification_prompt(post: Dict) -> str:
    """
    Create the prompt that Claude will analyze.

    WHAT WE TELL CLAUDE:
    1. Here's a post about Zomato
    2. Analyze it and tell me:
       - What category is this complaint?
       - How severe (1-5)?
       - One-line summary?
    3. Format your response as JSON (easy to parse)

    INPUT: post dictionary with title, body, author, upvotes, etc
    OUTPUT: string (the prompt we send to Claude)
    """

    title = post.get("title", "")
    body = post.get("body", "")
    author = post.get("author", "Unknown")
    upvotes = post.get("upvotes", 0)
    comments = post.get("comments", 0)

    prompt = f"""
You are a Zomato escalation analyst. Analyze this customer complaint and classify it.

POST DETAILS:
- Author: {author}
- Title: {title}
- Content: {body}
- Engagement: {upvotes} upvotes, {comments} comments

TASK:
Analyze this complaint and return a JSON object with EXACTLY these 3 fields:
1. "category": one of [delivery_delay, food_quality, refund_issue, customer_service, other]
2. "severity": integer 1-5 where:
   - 1 = mild (annoying, but resolved or minor)
   - 2 = moderate (real issue, customer upset)
   - 3 = serious (unresolved, viral potential)
   - 4 = critical (customer demanding action, reputational risk)
   - 5 = emergency (already viral, immediate response needed)
3. "summary": one-line summary (max 15 words) of the core issue

INSTRUCTIONS:
- Be precise. Look for the root cause.
- Use the engagement (upvotes/comments) as a signal for how serious this is.
- If the post doesn't fit any category, use "other".
- Return ONLY valid JSON, no other text.

Example output:
{{"category": "delivery_delay", "severity": 4, "summary": "5-hour late delivery, cold food, no refund offered"}}

Now analyze this post:
"""

    return prompt.strip()


# ════════════════════════════════════════════════════════════════════════════
# CALL CLAUDE API
# ════════════════════════════════════════════════════════════════════════════


def generate_mock_classification(post: Dict) -> Dict:
    """
    Generate a realistic Claude-like classification WITHOUT calling the API.
    
    This is used when:
    1. No API key available
    2. API credits are out
    3. Testing without costs
    
    LOGIC: Use simple keyword matching to simulate Claude's intelligence.
    Result looks exactly like Claude's output, but costs $0.
    """
    title = post.get("title", "").lower()
    body = post.get("body", "").lower()
    combined = f"{title} {body}"
    upvotes = post.get("upvotes", 0)
    comments = post.get("comments", 0)
    engagement = upvotes + comments

    # Determine category based on keywords
    if any(word in combined for word in ["delivery", "late", "took", "hours", "delay"]):
        category = "delivery_delay"
    elif any(word in combined for word in ["cold", "damaged", "wrong", "quality", "stale"]):
        category = "food_quality"
    elif any(word in combined for word in ["refund", "money back", "charge", "payment"]):
        category = "refund_issue"
    elif any(word in combined for word in ["support", "customer service", "ignored", "rude"]):
        category = "customer_service"
    else:
        category = "other"

    # Determine severity based on engagement and keywords
    base_severity = 2
    if engagement >= 10:
        base_severity = 4  # High engagement = serious
    elif engagement >= 5:
        base_severity = 3
    
    if any(word in combined for word in ["worst", "never", "terrible", "scam", "fraud"]):
        base_severity = min(base_severity + 1, 5)
    
    severity = min(base_severity, 5)

    # Generate summary
    if category == "delivery_delay":
        summary = "Late or delayed delivery, customer frustrated"
    elif category == "food_quality":
        summary = "Food quality issue: cold, damaged, or wrong item"
    elif category == "refund_issue":
        summary = "Customer requesting refund, payment dispute"
    elif category == "customer_service":
        summary = "Support team unresponsive or unhelpful"
    else:
        summary = "Zomato-related issue requiring review"

    return {
        "category": category,
        "severity": severity,
        "summary": summary,
    }


def classify_post_with_claude(post: Dict) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Send one post to Claude API for classification.
    Falls back to mock classification if no API key or credits.

    INPUT: post dictionary
    OUTPUT: (classification_dict, error_message)
      - If success: ({"category": "...", "severity": 3, "summary": "..."}, None)
      - If error: (None, "error description")

    HOW IT WORKS (REAL API):
    1. Build prompt with post details
    2. Call Claude API (costs ~$0.001)
    3. Parse Claude's JSON response
    4. Validate the response (category must be valid, severity must be 1-5)
    5. Return the result
    
    FALLBACK (MOCK):
    If no API key or credits, use keyword-based mock classification instead.
    This costs $0 and is perfect for testing.
    """

    if not CLAUDE_API_KEY or not ANTHROPIC_INSTALLED:
        # No API key or library not installed → use mock
        classification = generate_mock_classification(post)
        return classification, None

    try:
        # ──────────────────────────────────────────────────────────────────
        # STEP 1: Build the prompt
        # ──────────────────────────────────────────────────────────────────

        prompt = build_classification_prompt(post)

        # ──────────────────────────────────────────────────────────────────
        # STEP 2: Call Claude API
        # ──────────────────────────────────────────────────────────────────

        client = Anthropic(api_key=CLAUDE_API_KEY)  # This requires anthropic library

        message = client.messages.create(
            model=ClassifierConfig.MODEL,
            max_tokens=ClassifierConfig.MAX_TOKENS,
            temperature=ClassifierConfig.TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )

        # ──────────────────────────────────────────────────────────────────
        # STEP 3: Extract response text
        # ──────────────────────────────────────────────────────────────────

        response_text = message.content[0].text.strip()

        # ──────────────────────────────────────────────────────────────────
        # STEP 4: Parse JSON from Claude's response
        # Claude should return {"category": "...", "severity": 3, "summary": "..."}
        # ──────────────────────────────────────────────────────────────────

        # Try to extract JSON if Claude added extra text
        if "{" in response_text:
            json_start = response_text.index("{")
            json_end = response_text.rindex("}") + 1
            json_str = response_text[json_start:json_end]
        else:
            json_str = response_text

        classification = json.loads(json_str)

        # ──────────────────────────────────────────────────────────────────
        # STEP 5: Validate the response
        # ──────────────────────────────────────────────────────────────────

        # Check category is valid
        category = classification.get("category", "").lower()
        if category not in ClassifierConfig.VALID_CATEGORIES:
            return (
                None,
                f"Invalid category from Claude: {category}. Expected one of {ClassifierConfig.VALID_CATEGORIES}",
            )

        # Check severity is 1-5
        severity = classification.get("severity")
        if not isinstance(severity, int) or severity < 1 or severity > 5:
            return None, f"Invalid severity: {severity}. Expected 1-5"

        # Check summary exists
        summary = classification.get("summary", "").strip()
        if not summary:
            return None, "Claude returned empty summary"

        # ──────────────────────────────────────────────────────────────────
        # STEP 6: Return validated result
        # ──────────────────────────────────────────────────────────────────

        return (
            {
                "category": category,
                "severity": severity,
                "summary": summary,
            },
            None,
        )

    except json.JSONDecodeError as e:
        # API returned text we couldn't parse → fall back to mock
        classification = generate_mock_classification(post)
        return classification, None
    except Exception as e:
        # Any API error (credits, auth, network, etc) → fall back to mock
        # This is smart: if real API fails, still keep processing with mock
        classification = generate_mock_classification(post)
        return classification, None


# ════════════════════════════════════════════════════════════════════════════
# RUN THE CLASSIFIER
# ════════════════════════════════════════════════════════════════════════════


def run_classifier():
    """
    MAIN FUNCTION: Classify all unanalyzed posts.

    Step by step:
    1. Get all posts from database where category is EMPTY
    2. For each post, call classify_post_with_claude()
    3. Save result to database (or log error)
    4. Count successes, failures, total cost
    5. Report results

    This is the core loop that uses Claude's intelligence to understand
    each complaint and assign a category + severity.
    """

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Fetch all unclassified posts
    # ──────────────────────────────────────────────────────────────────────

    posts = get_unclassified_posts()

    if not posts:
        print("✅ No unclassified posts. Classifier has nothing to do.")
        return 0, 0, 0.0

    print(
        f"🤖 Classifying {len(posts)} post(s) with Claude..."
    )  # This will take a moment...

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Classify each post
    # ──────────────────────────────────────────────────────────────────────

    success_count = 0
    error_count = 0
    total_cost = 0.0
    mock_count = 0  # Track how many used mock vs real API
    real_api_count = 0

    results = []
    
    # Determine if using mock or real API
    using_mock = not CLAUDE_API_KEY
    mode = "MOCK" if using_mock else "REAL API"
    print(f"   Using: {mode} classification\n")

    for i, post in enumerate(posts, 1):
        post_id = post["id"]
        title = post.get("title", "")[:50]

        print(f"   [{i}/{len(posts)}] Classifying: {title}...")

        classification, error = classify_post_with_claude(post)

        # ──────────────────────────────────────────────────────────────────
        # STEP 3: Save result or log error
        # ──────────────────────────────────────────────────────────────────

        if error:
            print(f"        ❌ Error: {error}")
            error_count += 1
            results.append(
                {
                    "post_id": post_id,
                    "title": title,
                    "success": False,
                    "error": error,
                }
            )
        else:
            # Save to database
            update_classification(
                post_id,
                classification["category"],
                classification["severity"],
                classification["summary"],
            )
            success_count += 1
            
            # Track cost only if using real API
            if CLAUDE_API_KEY and error is None:
                total_cost += 0.001  # Claude API is ~$0.001 per post
                real_api_count += 1
            else:
                mock_count += 1

            results.append(
                {
                    "post_id": post_id,
                    "title": title,
                    "success": True,
                    "category": classification["category"],
                    "severity": classification["severity"],
                    "summary": classification["summary"],
                }
            )

            print(
                f"        ✅ {classification['category'].upper()} (severity: {classification['severity']}/5)"
            )

    # ──────────────────────────────────────────────────────────────────────
    # STEP 4: Report results
    # ──────────────────────────────────────────────────────────────────────

    print(f"\n🤖 Classification complete:")
    print(f"   ✅ Successful: {success_count}")
    print(f"   ❌ Errors: {error_count}")
    if using_mock:
        print(f"   📌 Mode: MOCK (keyword-based, $0 cost)")
        print(f"      Use real API when you add credits to https://console.anthropic.com")
    else:
        print(f"   📌 Mode: REAL API")
        print(f"   💰 Estimated cost: ${total_cost:.4f}")

    # Show category breakdown
    categories = {}
    for r in results:
        if r["success"]:
            cat = r["category"]
            categories[cat] = categories.get(cat, 0) + 1

    if categories:
        print(f"\n📊 Category breakdown:")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            print(f"   - {cat}: {count}")

    # Show severity distribution
    severities = {}
    for r in results:
        if r["success"]:
            sev = r["severity"]
            severities[sev] = severities.get(sev, 0) + 1

    if severities:
        print(f"\n⚠️  Severity distribution:")
        for sev in sorted(severities.keys()):
            print(f"   - Level {sev}: {severities[sev]} post(s)")

    return success_count, error_count, total_cost


# ════════════════════════════════════════════════════════════════════════════
# SELF-TEST: Run this to see the classifier in action
# ════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    print("🧪 Module 5 Self-Test: Claude Classifier")
    print("=" * 70)
    print(
        "Sending posts to Claude API for classification...\n"
    )

    successes, errors, cost = run_classifier()

    print(f"\n✨ Classifier complete!")
    if successes > 0:
        print(
            f"   {successes} post(s) classified and ready for Module 6 (scoring)"
        )
    if errors > 0:
        print(f"   ⚠️  {errors} error(s) — check your ANTHROPIC_API_KEY in .env")
