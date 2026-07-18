"""
action/escalator.py — Module 7: Action / Escalation Handler

════════════════════════════════════════════════════════════════════════════
WHAT THIS MODULE DOES (in plain English)
════════════════════════════════════════════════════════════════════════════

At this point in the pipeline, we have:
  ✅ Post details (title, body, author, engagement)
  ✅ Classification (category, severity)
  ✅ Escalation score (0-100)

Now: TIME TO ACT.

If a post scored 80+ (CRITICAL) or 60+ (HIGH), we fire actions:
  1. Send Slack message to #zomato-escalations channel
  2. Create Jira ticket (assigned to Zomato team)
  3. Send email alert to manager
  4. Log everything (for audit trail)

EXAMPLES:

CRITICAL Post (score 95):
  "Zomato delivery never arrived, customer demands refund, post has 50+ upvotes"
  
  Actions fired:
    ✅ Slack: 🔴 CRITICAL [delivery_delay] Score: 95/100
                "Order never arrived - customer very upset - 50 upvotes"
                [Link to post] [View in dashboard]
    ✅ Jira: New ticket "Urgent: Delivery Never Arrived - Customer Escalation"
                Priority: Highest
                Assigned to: On-call Support Manager
                Description: Post details + link + customer contact info
    ✅ Email: Alert sent to support-manager@zomato.com
    ✅ Database: Mark escalated = 1, log "Slack + Jira + Email sent at 2026-07-18 16:30"

HIGH Post (score 72):
  "Zomato delivery 2 hours late, cold food, low engagement (8 upvotes)"
  
  Actions fired:
    ✅ Slack: 🟠 HIGH [delivery_delay] Score: 72/100
                "Late delivery + cold food - 8 upvotes"
                [Link] [View]
    ✅ Jira: New ticket (Priority: High)
    ❌ Email: Not sent for HIGH (only for CRITICAL)
    ✅ Database: Mark escalated = 1

MODERATE Post (score 45):
  "Complaint about wait time, low engagement"
  
  Actions: None fired
    → Post is logged in database but no alerts sent
    → Humans can review on dashboard if needed

WHY THIS IS SMART:
  - Automates the boring parts (no manual Slack posting)
  - Prevents alert fatigue (only CRITICAL/HIGH get alerts)
  - Creates audit trail (who did what, when)
  - Integrates with company tools (Slack, Jira)
  - Easy to disable/adjust thresholds
  
THINK OF IT AS:
  A security system that:
  - Detects alarm (scorer sets score)
  - Validates it's real (Module 7 checks thresholds)
  - Takes action (calls police/alarm company)
  - Logs it (creates incident record)
════════════════════════════════════════════════════════════════════════════
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

# So this module can import from database/
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import (
    get_recent_posts,
    mark_escalated,
    get_connection,
)

load_dotenv()


# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION: Action thresholds and settings
# ════════════════════════════════════════════════════════════════════════════


class ActionConfig:
    """
    All action settings in one place.
    Tune these to control when alerts fire.
    """

    # ──────────────────────────────────────────────────────────────────────
    # ALERT THRESHOLDS: When to fire actions
    # ──────────────────────────────────────────────────────────────────────

    # Score >= this → send ALL alerts (Slack + Jira + Email)
    CRITICAL_THRESHOLD = 80

    # Score >= this (but < CRITICAL) → send Slack + Jira (no email)
    HIGH_THRESHOLD = 60

    # Score >= this (but < HIGH) → log only (no alerts)
    MODERATE_THRESHOLD = 40

    # ──────────────────────────────────────────────────────────────────────
    # SLACK CONFIGURATION
    # ──────────────────────────────────────────────────────────────────────

    # Slack webhook URL for escalations channel
    # Get this from: Slack App → Incoming Webhooks → Add webhook for #zomato-escalations
    # For mock mode: leave empty, we'll simulate
    SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")

    # Slack channel to post to (used in mock mode)
    SLACK_CHANNEL = "#zomato-escalations"

    # ──────────────────────────────────────────────────────────────────────
    # JIRA CONFIGURATION
    # ──────────────────────────────────────────────────────────────────────

    # JIRA instance URL (e.g., https://zomato.atlassian.net)
    JIRA_URL = os.getenv("JIRA_URL", "")

    # JIRA project key (e.g., "ZOM" for Zomato)
    JIRA_PROJECT = os.getenv("JIRA_PROJECT", "ZOM")

    # JIRA API token (from your JIRA account settings)
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

    # ──────────────────────────────────────────────────────────────────────
    # EMAIL CONFIGURATION
    # ──────────────────────────────────────────────────────────────────────

    # Email to notify for CRITICAL alerts
    CRITICAL_EMAIL = os.getenv("CRITICAL_ALERT_EMAIL", "support-manager@zomato.com")

    # Email service (mock only, we don't call real email APIs)
    EMAIL_ENABLED = False  # Set to True only if you integrate real email

    # ──────────────────────────────────────────────────────────────────────
    # MOCK MODE (testing without real APIs)
    # ──────────────────────────────────────────────────────────────────────

    # If True, we simulate actions without calling real Slack/Jira
    # This lets you test without API credentials
    MOCK_MODE = True  # Set to False when you have real API keys

    # Log file for mock mode (so you can see what "would have" happened)
    MOCK_LOG_FILE = "action_log.txt"


# ════════════════════════════════════════════════════════════════════════════
# ACTION FUNCTIONS: What we do for each post
# ════════════════════════════════════════════════════════════════════════════


def send_slack_alert(post: Dict, score: float, risk_level: str) -> Tuple[bool, str]:
    """
    Send a Slack message to the escalations channel.

    INPUT: post dict, score, risk_level ("CRITICAL", "HIGH", etc)
    OUTPUT: (success, message)
      - If success: (True, "Message sent to #zomato-escalations")
      - If error: (False, "Error description")

    WHAT THE MESSAGE LOOKS LIKE:
      🔴 CRITICAL [delivery_delay] Score: 95/100
      Order never arrived - customer very upset - 50 upvotes
      Author: @upset_customer
      [Link] [View in Dashboard]

    If MOCK_MODE:
      → Just log it, don't actually post
    """

    if ActionConfig.MOCK_MODE:
        message = (
            f"SLACK: {risk_level} {post.get('category')} | "
            f"Score {score:.0f} | {post.get('title', '')[:60]}"
        )
        log_action(message)
        return True, f"Mock Slack sent to {ActionConfig.SLACK_CHANNEL}"

    # Real Slack mode (requires SLACK_WEBHOOK in .env)
    if not ActionConfig.SLACK_WEBHOOK:
        return (
            False,
            "No SLACK_WEBHOOK_URL in .env (mock mode will be used)",
        )

    try:
        import requests

        # Format message
        emoji = "🔴" if "CRITICAL" in risk_level else "🟠"
        title = post.get("title", "")[:80]
        author = post.get("author", "Unknown")
        upvotes = post.get("upvotes", 0)
        comments = post.get("comments", 0)
        category = post.get("category", "unknown").upper()

        slack_message = {
            "text": f"{emoji} {risk_level} Escalation (Score: {score:.0f}/100)",
            "attachments": [
                {
                    "color": "danger" if "CRITICAL" in risk_level else "warning",
                    "fields": [
                        {"title": "Category", "value": category, "short": True},
                        {"title": "Severity", "value": f"{post.get('severity', 0)}/5", "short": True},
                        {"title": "Title", "value": title, "short": False},
                        {"title": "Author", "value": author, "short": True},
                        {"title": "Engagement", "value": f"{upvotes} upvotes, {comments} comments", "short": True},
                        {"title": "Summary", "value": post.get("summary", ""), "short": False},
                    ],
                }
            ],
        }

        response = requests.post(
            ActionConfig.SLACK_WEBHOOK,
            json=slack_message,
            timeout=5,
        )
        response.raise_for_status()

        return True, "Slack alert sent"

    except Exception as e:
        return False, f"Slack error: {str(e)}"


def create_jira_ticket(post: Dict, score: float, risk_level: str) -> Tuple[bool, str]:
    """
    Create a Jira ticket for high-priority posts.

    INPUT: post dict, score, risk_level
    OUTPUT: (success, ticket_id_or_error)
      - If success: (True, "ZOM-1234")
      - If error: (False, "Error description")

    TICKET TEMPLATE:
      Title: "[CRITICAL] Delivery Delay - Customer Very Upset"
      Priority: Highest (for CRITICAL), High (for HIGH)
      Description:
        Post: "Order never arrived, support ignored me"
        Score: 95/100
        Category: delivery_delay
        Severity: 4/5
        Engagement: 50 upvotes, 23 comments
        Author: @upset_customer
        Link: [Reddit link]
      Assigned to: On-call Support Manager
      Labels: escalation, urgent

    If MOCK_MODE:
      → Just log it, don't actually create Jira ticket
    """

    if ActionConfig.MOCK_MODE:
        ticket_id = f"MOCK-{post['id']}"
        priority = "Highest" if "CRITICAL" in risk_level else "High"
        message = (
            f"JIRA: New ticket {ticket_id} | "
            f"Priority: {priority} | "
            f"Category: {post.get('category')} | "
            f"Title: {post.get('title', '')[:60]}"
        )
        log_action(message)
        return True, ticket_id

    # Real Jira mode (requires JIRA_URL, JIRA_API_TOKEN in .env)
    if not ActionConfig.JIRA_URL or not ActionConfig.JIRA_API_TOKEN:
        return (
            False,
            "No JIRA credentials in .env (mock mode will be used)",
        )

    try:
        import requests
        from requests.auth import HTTPBasicAuth

        priority = "Highest" if "CRITICAL" in risk_level else "High"
        title = post.get("title", "")[:100]
        category = post.get("category", "unknown").upper()

        # JIRA ticket payload
        jira_payload = {
            "fields": {
                "project": {"key": ActionConfig.JIRA_PROJECT},
                "summary": f"[{risk_level}] {category} - {title}",
                "description": (
                    f"Post: {post.get('title', '')}\n"
                    f"Author: {post.get('author', '')}\n"
                    f"Score: {score:.0f}/100\n"
                    f"Category: {category}\n"
                    f"Severity: {post.get('severity', 0)}/5\n"
                    f"Engagement: {post.get('upvotes', 0)} upvotes, {post.get('comments', 0)} comments\n"
                    f"Summary: {post.get('summary', '')}\n"
                ),
                "issuetype": {"name": "Bug"},
                "priority": {"name": priority},
                "labels": ["escalation", "social-listening"],
            }
        }

        # Create ticket
        response = requests.post(
            f"{ActionConfig.JIRA_URL}/rest/api/3/issue",
            json=jira_payload,
            auth=HTTPBasicAuth("your-email@zomato.com", ActionConfig.JIRA_API_TOKEN),
            timeout=5,
        )
        response.raise_for_status()

        ticket_id = response.json().get("key", "UNKNOWN")
        return True, ticket_id

    except Exception as e:
        return False, f"Jira error: {str(e)}"


def send_email_alert(post: Dict, score: float, risk_level: str) -> Tuple[bool, str]:
    """
    Send email alert (only for CRITICAL posts).

    INPUT: post dict, score, risk_level
    OUTPUT: (success, message)

    EMAIL TEMPLATE:
      Subject: 🔴 CRITICAL ALERT: Zomato Post Escalation (Score: 95/100)
      
      Body:
        A high-severity post about Zomato has been detected and needs immediate attention.
        
        Post Details:
        - Title: "Order never arrived, support ignored me"
        - Category: Delivery Delay
        - Severity: 4/5
        - Score: 95/100
        - Author: @upset_customer
        - Engagement: 50 upvotes, 23 comments
        
        Action Items:
        1. Review the post on the dashboard
        2. Contact the customer for resolution
        3. See related Jira ticket: ZOM-1234
        
        Link: [Reddit link]

    If MOCK_MODE:
      → Just log it, don't send real email
    """

    if ActionConfig.MOCK_MODE:
        message = (
            f"EMAIL: Alert sent to {ActionConfig.CRITICAL_EMAIL} | "
            f"Subject: CRITICAL POST - {post.get('title', '')[:50]}"
        )
        log_action(message)
        return True, f"Mock email sent to {ActionConfig.CRITICAL_EMAIL}"

    # Real email mode (would require SMTP setup)
    if not ActionConfig.EMAIL_ENABLED:
        return (
            False,
            "Email not configured (mock mode will be used)",
        )

    # This is where you'd integrate real email (e.g., with SendGrid, AWS SES)
    # For now, mock mode only
    return True, "Email (mock)"


def log_action(message: str):
    """
    Log all actions to a file for audit trail.

    INPUT: action message (e.g., "Slack alert sent to #escalations")
    OUTPUT: writes to action_log.txt
    """

    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = f"[{timestamp}] {message}\n"

    try:
        with open(ActionConfig.MOCK_LOG_FILE, "a") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"❌ Failed to log action: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# MAIN ESCALATION LOGIC
# ════════════════════════════════════════════════════════════════════════════


def escalate_post(post: Dict) -> Tuple[str, List[str]]:
    """
    Determine risk level and fire appropriate actions.

    INPUT: post dict with score
    OUTPUT: (risk_level, actions_taken)
      - risk_level: "CRITICAL", "HIGH", "MODERATE", "LOW"
      - actions_taken: ["Slack alert sent", "Jira ticket ZOM-123 created", ...]

    LOGIC:
    1. Determine risk level based on score
    2. If CRITICAL: fire Slack + Jira + Email
    3. If HIGH: fire Slack + Jira (no email)
    4. If MODERATE/LOW: no actions (just log)
    5. Mark post as escalated in database
    """

    score = post.get("score", 0)
    actions = []

    # Determine risk level
    if score >= ActionConfig.CRITICAL_THRESHOLD:
        risk_level = "CRITICAL"
    elif score >= ActionConfig.HIGH_THRESHOLD:
        risk_level = "HIGH"
    elif score >= ActionConfig.MODERATE_THRESHOLD:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"

    # Fire actions based on risk level
    if risk_level == "CRITICAL":
        # CRITICAL: All alerts
        success, msg = send_slack_alert(post, score, f"🔴 {risk_level}")
        if success:
            actions.append(f"Slack alert sent ({msg})")

        success, ticket_id = create_jira_ticket(post, score, f"🔴 {risk_level}")
        if success:
            actions.append(f"Jira ticket created: {ticket_id}")

        success, msg = send_email_alert(post, score, f"🔴 {risk_level}")
        if success:
            actions.append(f"Email alert sent ({msg})")

    elif risk_level == "HIGH":
        # HIGH: Slack + Jira only
        success, msg = send_slack_alert(post, score, f"🟠 {risk_level}")
        if success:
            actions.append(f"Slack alert sent ({msg})")

        success, ticket_id = create_jira_ticket(post, score, f"🟠 {risk_level}")
        if success:
            actions.append(f"Jira ticket created: {ticket_id}")

    else:
        # MODERATE/LOW: No actions, just log
        log_action(f"Post #{post['id']}: {risk_level} (Score: {score:.0f}) - No action taken")
        actions.append("Logged for review (no alert)")

    return risk_level, actions


# ════════════════════════════════════════════════════════════════════════════
# RUN ESCALATION
# ════════════════════════════════════════════════════════════════════════════


def run_escalator():
    """
    MAIN FUNCTION: Process all posts and fire escalation actions.

    Step by step:
    1. Get all recent posts from database (just the scored ones)
    2. For each post where escalated = 0 (not yet actioned):
       - Determine risk level
       - Fire actions (Slack, Jira, email)
       - Mark escalated = 1 in database
       - Log what happened
    3. Report summary

    This is the final step: when a post hits this module, it becomes a
    customer service incident (Slack alert, Jira ticket, email to manager).
    """

    # ──────────────────────────────────────────────────────────────────────
    # STEP 1: Get all recent posts that need escalation
    # ──────────────────────────────────────────────────────────────────────

    posts = get_recent_posts(limit=100)

    # Filter to only posts that have scores and aren't yet escalated
    posts_to_escalate = [p for p in posts if p.get("score") and p.get("escalated") == 0]

    if not posts_to_escalate:
        print("✅ No posts to escalate. All done!")
        return {}

    print(
        f"🚨 Processing {len(posts_to_escalate)} post(s) for escalation...\n"
    )

    # ──────────────────────────────────────────────────────────────────────
    # STEP 2: Escalate each post
    # ──────────────────────────────────────────────────────────────────────

    results = []
    risk_breakdown = {}

    for i, post in enumerate(posts_to_escalate, 1):
        post_id = post["id"]
        title = post.get("title", "")[:50]
        score = post.get("score", 0)

        risk_level, actions = escalate_post(post)

        # Update database: mark as escalated
        actions_log = " | ".join(actions)
        mark_escalated(post_id, actions_log)

        results.append(
            {
                "post_id": post_id,
                "title": title,
                "score": score,
                "risk_level": risk_level,
                "actions": actions,
            }
        )

        # Track risk level breakdown
        risk_breakdown[risk_level] = risk_breakdown.get(risk_level, 0) + 1

        # Print summary
        emoji = "🔴" if risk_level == "CRITICAL" else "🟠" if risk_level == "HIGH" else "🟡"
        print(
            f"   [{i}] {emoji} {risk_level}: Score {score:.0f} | {title}..."
        )
        for action in actions:
            print(f"       → {action}")

    # ──────────────────────────────────────────────────────────────────────
    # STEP 3: Report results
    # ──────────────────────────────────────────────────────────────────────

    print(f"\n🚨 Escalation complete:")
    print(f"   Total posts processed: {len(posts_to_escalate)}")

    print(f"\n📊 Risk breakdown:")
    for risk in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
        count = risk_breakdown.get(risk, 0)
        if count > 0:
            emoji = "🔴" if risk == "CRITICAL" else "🟠" if risk == "HIGH" else "🟡" if risk == "MODERATE" else "🟢"
            print(f"   {emoji} {risk}: {count}")

    # Summary of actions
    critical_count = risk_breakdown.get("CRITICAL", 0)
    high_count = risk_breakdown.get("HIGH", 0)
    slack_alerts = critical_count + high_count

    print(f"\n✅ Actions fired:")
    print(f"   Slack alerts: {slack_alerts}")
    print(f"   Jira tickets: {slack_alerts}")
    print(f"   Email alerts: {critical_count}")

    if ActionConfig.MOCK_MODE:
        print(f"\n📌 Running in MOCK MODE")
        print(f"   View action log: {ActionConfig.MOCK_LOG_FILE}")
        print(
            f"   To use real Slack/Jira, add credentials to .env and set MOCK_MODE=False"
        )

    return risk_breakdown


# ════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    print("🧪 Module 7 Self-Test: Action / Escalator")
    print("=" * 70)
    print("Processing posts and firing escalation actions...\n")

    risk_breakdown = run_escalator()

    print(f"\n✨ Escalator complete!")
    if risk_breakdown:
        total_alerts = (
            risk_breakdown.get("CRITICAL", 0) + risk_breakdown.get("HIGH", 0)
        )
        if total_alerts > 0:
            print(f"   ⚠️  {total_alerts} alert(s) sent (Slack, Jira, email)")
        else:
            print(f"   ℹ️  No critical posts — all handled gracefully")
