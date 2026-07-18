"""
pipeline/scorer.py — Module 6: Escalation Scorer

════════════════════════════════════════════════════════════════════════════
WHAT THIS MODULE DOES (in plain English)
════════════════════════════════════════════════════════════════════════════

At this point in the pipeline, each post has been classified:
  ✅ Passed pre-filter (Module 4)
  ✅ Claude assigned category (Module 5)
  ✅ Claude assigned severity 1-5 (Module 5)

Now we need ONE MORE THING: a final 0-100 ESCALATION SCORE that answers:
  "Should Zomato take action on this post?"

EXAMPLES:
  Score 95 → EMERGENCY: Post is viral, many complaints, customer is furious
            → Action: Immediate Slack alert + create Jira ticket
  
  Score 75 → CRITICAL: Real issue, affects multiple customers, reputation risk
            → Action: Send Slack alert, assign to manager
  
  Score 45 → MODERATE: Valid complaint but isolated, low engagement
            → Action: Log for review, no urgent action
  
  Score 15 → LOW: Single complaint, low engagement, probably resolved already
            → Action: Archive, monitor

HOW THE SCORE IS CALCULATED:
  Base score = severity × 20 (severity is 1-5, so max 100)
  
  Category multiplier:
    - refund_issue: 1.5x (customer wants money, high chargeback risk)
    - customer_service: 1.4x (unhappy customer, might post more)
    - delivery_delay: 1.2x (operational issue, affects reputation)
    - food_quality: 1.1x (individual order issue, less systemic)
    - other: 1.0x (unclear)
  
  Engagement bonus:
    - Upvotes: +1 per upvote (max +30)
    - Comments: +2 per comment (more engagement = higher priority)
  
  Final score = min(base × category_multiplier + engagement_bonus, 100)

EXAMPLE CALCULATION:
  Post: "Order never arrived, support ignored me for 3 days"
  
  Severity: 4 (assigned by Claude)
  Category: refund_issue (assigned by Claude)
  Upvotes: 12
  Comments: 8
  
  Base score = 4 × 20 = 80
  Category multiplier = 1.5 (refund)
  Score after category = 80 × 1.5 = 120 (capped at 100)
  Engagement bonus = min(12, 30) + (8 × 2) = 12 + 16 = 28
  Final score = min(120 + 28, 100) = 100 → EMERGENCY
  
  Verdict: "This post is critical, customer might do a chargeback"

WHY THIS IS SMART:
  - Combines Claude's judgment (severity, category) with data (engagement)
  - Transparent: anyone can see why a post got its score
  - Easy to adjust: change multipliers to tune urgency
  - Actionable: score directly determines if Slack alert fires
  
THINK OF IT AS:
  A triage nurse at a hospital:
  - High fever (severity) + many people noticing (engagement) + needs surgery (category)
  = Critical, send to OR immediately
  - Mild headache (severity) + nobody noticing (engagement)
  = Low priority, monitor at home
════════════════════════════════════════════════════════════════════════════
"""

import sys
from pathlib import Path
from typing import Dict, Tuple
import math

# So this module can import from database/
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import get_unscored_posts, update_score


# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION: Scoring weights and multipliers
# ════════════════════════════════════════════════════════════════════════════


class ScorerConfig:
    """
    All scoring parameters in one place.
    Tune these to adjust what counts as high-risk.
    """

    # ──────────────────────────────────────────────────────────────────────
    # BASE SCORE: Severity mapping
    # Severity is 1-5 from Claude, we convert to base score
    # ──────────────────────────────────────────────────────────────────────

    # Points per severity level (severity × this value)
    # Severity 5 (emergency) = 5 × 20 = 100 points (max)
    SEVERITY_MULTIPLIER = 20

    # ──────────────────────────────────────────────────────────────────────
    # CATEGORY MULTIPLIERS: Some issues are more urgent than others
    # Applied to base score: score = base_score × category_multiplier
    # ──────────────────────────────────────────────────────────────────────

    CATEGORY_MULTIPLIERS = {
        "refund_issue": 1.5,  # Highest risk: customer wants money, chargeback
        "customer_service": 1.4,  # High risk: unhappy customer, might escalate
        "delivery_delay": 1.2,  # Medium risk: operational issue, affects reputation
        "food_quality": 1.1,  # Lower risk: usually isolated to one order
        "other": 1.0,  # Unknown category, neutral
    }

    # ──────────────────────────────────────────────────────────────────────
    # ENGAGEMENT BONUS: Viral signals
    # Posts with more upvotes/comments are more risky (higher visibility)
    # ──────────────────────────────────────────────────────────────────────

    # Points per upvote (people agreeing with the complaint)
    POINTS_PER_UPVOTE = 1

    # Maximum points from upvotes (don't let engagement dominate)
    MAX_UPVOTE_POINTS = 30

    # Points per comment (active discussion, more visibility)
    POINTS_PER_COMMENT = 2

    # ──────────────────────────────────────────────────────────────────────
    # FINAL SCORE: Boundaries for action
    # ──────────────────────────────────────────────────────────────────────

    # If score > this, it's critical (send urgent Slack alert)
    CRITICAL_THRESHOLD = 80

    # If score > this, it's high (send normal Slack alert)
    HIGH_THRESHOLD = 60

    # If score > this, it's moderate (log for review)
    MODERATE_THRESHOLD = 40

    # If score <= this, it's low (archive, monitor)
    # (everything below LOW_THRESHOLD is archived)


# ════════════════════════════════════════════════════════════════════════════
# SCORING LOGIC
# ════════════════════════════════════════════════════════════════════════════


def calculate_escalation_score(post: Dict) -> Tuple[float, str]:
    """
    Calculate the final 0-100 escalation score for one post.

    INPUT: post dictionary with category, severity, upvotes, comments
    OUTPUT: (score, risk_level_string)
      Example: (85.5, "CRITICAL")

    HOW IT WORKS:
    1. Extract severity, category, and engagement from post
    2. Calculate base score from severity
    3. Apply category multiplier (some types are higher risk)
    4. Add engagement bonus (viral signals)
    5. Cap at 100
    6. Determine risk level (CRITICAL, HIGH, MODERATE, LOW)
    7. Return score and risk level
    """

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Extract data from post
    # ──────────────────────────────────────────────────────────────────────

    severity = post.get("severity", 3)  # default to moderate if missing
    category = post.get("category", "other").lower()
    upvotes = post.get("upvotes", 0)
    comments = post.get("comments", 0)

    title = post.get("title", "")
    body = post.get("body", "")

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Calculate base score from severity
    # Severity 1-5 → score 20-100
    # ──────────────────────────────────────────────────────────────────────

    base_score = severity * ScorerConfig.SEVERITY_MULTIPLIER

    # ──────────────────────────────────────────────────────────────────────
    # STEP 3: Apply category multiplier
    # Some complaint types are higher risk
    # ──────────────────────────────────────────────────────────────────────

    category_multiplier = ScorerConfig.CATEGORY_MULTIPLIERS.get(category, 1.0)
    score_after_category = base_score * category_multiplier

    # ──────────────────────────────────────────────────────────────────────
    # STEP 4: Add engagement bonus
    # More upvotes/comments = more visibility = higher urgency
    # ──────────────────────────────────────────────────────────────────────

    upvote_points = min(
        upvotes * ScorerConfig.POINTS_PER_UPVOTE,
        ScorerConfig.MAX_UPVOTE_POINTS,
    )
    comment_points = comments * ScorerConfig.POINTS_PER_COMMENT

    engagement_bonus = upvote_points + comment_points

    # ──────────────────────────────────────────────────────────────────────
    # STEP 5: Final score (cap at 100)
    # ──────────────────────────────────────────────────────────────────────

    final_score = score_after_category + engagement_bonus
    final_score = min(final_score, 100)

    # ──────────────────────────────────────────────────────────────────────
    # STEP 6: Determine risk level based on score
    # ──────────────────────────────────────────────────────────────────────

    if final_score >= ScorerConfig.CRITICAL_THRESHOLD:
        risk_level = "🔴 CRITICAL"
    elif final_score >= ScorerConfig.HIGH_THRESHOLD:
        risk_level = "🟠 HIGH"
    elif final_score >= ScorerConfig.MODERATE_THRESHOLD:
        risk_level = "🟡 MODERATE"
    else:
        risk_level = "🟢 LOW"

    return final_score, risk_level


# ════════════════════════════════════════════════════════════════════════════
# RUN THE SCORER
# ════════════════════════════════════════════════════════════════════════════


def run_scorer():
    """
    MAIN FUNCTION: Score all unscored posts.

    Step by step:
    1. Get all posts from database where score is NULL
       (these are posts that Claude classified but haven't been scored yet)
    2. For each post, calculate_escalation_score()
    3. Save result to database
    4. Count by risk level
    5. Report results

    This creates the final number that Module 7 (Action) will use to decide
    if Slack alerts, Jira tickets, or manager escalations are needed.
    """

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Fetch all unscored posts
    # ──────────────────────────────────────────────────────────────────────

    posts = get_unscored_posts()

    if not posts:
        print("✅ No unscored posts. Scorer has nothing to do.")
        return {}

    print(f"📊 Scoring {len(posts)} post(s)...\n")

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Score each post
    # ──────────────────────────────────────────────────────────────────────

    results = []
    risk_breakdown = {}  # Count how many in each risk level

    for i, post in enumerate(posts, 1):
        post_id = post["id"]
        title = post.get("title", "")[:50]
        category = post.get("category", "?")
        severity = post.get("severity", "?")

        score, risk_level = calculate_escalation_score(post)

        # Save to database
        update_score(post_id, score)

        results.append(
            {
                "post_id": post_id,
                "title": title,
                "category": category,
                "severity": severity,
                "score": score,
                "risk_level": risk_level,
            }
        )

        # Track risk level breakdown
        risk_key = risk_level.split()[-1]  # Extract "CRITICAL", "HIGH", etc
        risk_breakdown[risk_key] = risk_breakdown.get(risk_key, 0) + 1

        print(
            f"   [{i}/{len(posts)}] {risk_level}: {score:5.1f} | {category:18} | {title}..."
        )

    # ──────────────────────────────────────────────────────────────────────
    # STEP 3: Report results
    # ──────────────────────────────────────────────────────────────────────

    print(f"\n📊 Scoring complete:")
    print(f"   Total posts scored: {len(posts)}")

    # Show risk breakdown
    print(f"\n⚠️  Risk level breakdown:")
    risk_order = ["CRITICAL", "HIGH", "MODERATE", "LOW"]
    for risk in risk_order:
        count = risk_breakdown.get(risk, 0)
        if count > 0:
            print(f"   - {risk}: {count}")

    # Calculate average score
    avg_score = sum(r["score"] for r in results) / len(results) if results else 0
    print(f"\n📈 Average escalation score: {avg_score:.1f}")

    # Show critical posts (these need immediate action)
    critical_posts = [r for r in results if "CRITICAL" in r["risk_level"]]
    if critical_posts:
        print(f"\n🔴 CRITICAL POSTS (Module 7 will action these):")
        for post in critical_posts:
            print(
                f"   - Post #{post['post_id']}: {post['title']}... ({post['score']:.1f})"
            )

    return risk_breakdown


# ════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    print("🧪 Module 6 Self-Test: Escalation Scorer")
    print("=" * 70)
    print("Calculating escalation scores for all classified posts...\n")

    risk_breakdown = run_scorer()

    print(f"\n✨ Scorer complete!")
    if risk_breakdown:
        critical_count = risk_breakdown.get("CRITICAL", 0)
        high_count = risk_breakdown.get("HIGH", 0)
        if critical_count > 0 or high_count > 0:
            print(
                f"   ⚠️  {critical_count + high_count} high-priority post(s) ready for Module 7 (Action)"
            )
        else:
            print(f"   ℹ️  All posts scored, no critical escalations needed")
