"""
dashboard/app.py — Module 8: Interactive Dashboard

════════════════════════════════════════════════════════════════════════════
WHAT THIS MODULE DOES (in plain English)
════════════════════════════════════════════════════════════════════════════

This is the visual heart of the project. A web dashboard that shows:
  1. All posts in a searchable, filterable table
  2. Real-time statistics (critical posts, average score, trends)
  3. Charts (category breakdown, severity distribution)
  4. Detailed post view (click any post to see full details)
  5. Status indicators (collector health, last run times)

WHO USES IT:
  - Zomato Support Manager: "Which posts need action today?"
  - Analyst: "What's the trending complaint type this week?"
  - Executive: "How much reputation risk do we have?" (at a glance)

EXAMPLE DASHBOARD VIEW:
  ┌─────────────────────────────────────────────────────────────┐
  │ Zomato Social Listening Dashboard                            │
  └─────────────────────────────────────────────────────────────┘
  
  📊 KEY METRICS
  ┌─────────────────┬─────────────────┬─────────────────┐
  │ CRITICAL Posts  │ Average Score   │ Total Posts     │
  │      6          │     92.5/100    │      48         │
  └─────────────────┴─────────────────┴─────────────────┘
  
  ⚠️  RISK BREAKDOWN
  ┌─────────────────┬─────────────────┬─────────────────┐
  │ 🔴 CRITICAL: 6  │ 🟠 HIGH: 12     │ 🟡 MODERATE: 18 │
  └─────────────────┴─────────────────┴─────────────────┘
  
  📈 CATEGORY TRENDS
  [Bar chart showing: delivery_delay (25 posts), refund_issue (12), etc]
  
  🔍 FILTERS
  Category: [All ▼]  Severity: [All ▼]  Score Range: [0 ▼] — [100 ▼]
  
  📋 ALL POSTS TABLE
  ┌────┬──────────────────────┬───────────────┬──────┬───────┐
  │ ID │ Title                │ Category      │Score │ Status│
  ├────┼──────────────────────┼───────────────┼──────┼───────┤
  │ 1  │ Order never arrived  │ delivery_delay│ 100  │✅ Act │
  │ 2  │ Cold food delivery   │ food_quality  │  95  │✅ Act │
  │ 3  │ Support was rude     │ cust_service  │  88  │✅ Act │
  └────┴──────────────────────┴───────────────┴──────┴───────┘
  
  [Click any row to see full details, social links, sentiment analysis]

WHY THIS IS SMART:
  - Real humans (managers) can make decisions based on data
  - Search + filter = find specific issues fast
  - Charts show patterns (not just individual posts)
  - Status page shows collector health (is Reddit still working?)
  - No coding needed to see results (just open web browser)
  
THINK OF IT AS:
  A control room for a nuclear plant:
  - Dials show real-time metrics (temperature, pressure)
  - Status lights show which systems are healthy (green) or failing (red)
  - Alarm bells ring for critical issues
  - Humans can make decisions from this one screen
════════════════════════════════════════════════════════════════════════════
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

# So this module can import from database/
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import get_recent_posts, get_source_statuses, get_connection

import streamlit as st


# ════════════════════════════════════════════════════════════════════════════
# PAGE CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Zomato Social Listening Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 Zomato Social Listening Dashboard")
st.markdown("Real-time monitoring of Zomato complaints across social media")


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR: FILTERS AND CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

st.sidebar.header("🔍 Filters & Settings")

# Auto-refresh toggle
auto_refresh = st.sidebar.checkbox("🔄 Auto-refresh (30s)", value=True)

# Category filter
st.sidebar.subheader("Filter by Category")
all_categories = ["All"] + [
    "delivery_delay",
    "food_quality",
    "refund_issue",
    "customer_service",
    "other",
]
selected_category = st.sidebar.selectbox(
    "Category:",
    all_categories,
    index=0,
)

# Severity filter
st.sidebar.subheader("Filter by Severity")
severity_range = st.sidebar.slider(
    "Severity (1-5):",
    min_value=1,
    max_value=5,
    value=(1, 5),
)

# Score range filter
st.sidebar.subheader("Filter by Escalation Score")
score_range = st.sidebar.slider(
    "Score (0-100):",
    min_value=0,
    max_value=100,
    value=(0, 100),
)

# Risk level filter
st.sidebar.subheader("Filter by Risk Level")
risk_levels = st.sidebar.multiselect(
    "Risk Levels:",
    ["🔴 CRITICAL", "🟠 HIGH", "🟡 MODERATE", "🟢 LOW"],
    default=["🔴 CRITICAL", "🟠 HIGH"],
)

# Search box
st.sidebar.subheader("Search Posts")
search_text = st.sidebar.text_input(
    "Search by title or author:",
    placeholder="Enter keywords...",
)


# ════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ════════════════════════════════════════════════════════════════════════════

def load_data():
    """
    Load all posts from database and apply filters.

    STEPS:
    1. Query database for recent posts
    2. Convert to DataFrame
    3. Add risk_level column based on score
    4. Apply all filters (category, severity, score, risk level, search)
    5. Sort by score (highest risk first)
    """

    posts = get_recent_posts(limit=500)

    if not posts:
        return pd.DataFrame()

    # Convert to DataFrame
    df = pd.DataFrame(posts)

    # Add risk_level column based on score
    def get_risk_level(score):
        if score >= 80:
            return "🔴 CRITICAL"
        elif score >= 60:
            return "🟠 HIGH"
        elif score >= 40:
            return "🟡 MODERATE"
        else:
            return "🟢 LOW"

    df["risk_level"] = df["score"].apply(get_risk_level)

    # Apply filters
    if selected_category != "All":
        df = df[df["category"] == selected_category]

    df = df[
        (df["severity"] >= severity_range[0])
        & (df["severity"] <= severity_range[1])
    ]

    df = df[
        (df["score"] >= score_range[0])
        & (df["score"] <= score_range[1])
    ]

    if risk_levels:
        df = df[df["risk_level"].isin(risk_levels)]

    if search_text:
        search_lower = search_text.lower()
        df = df[
            (df["title"].str.lower().str.contains(search_lower, na=False))
            | (df["author"].str.lower().str.contains(search_lower, na=False))
            | (df["body"].str.lower().str.contains(search_lower, na=False))
        ]

    # Sort by score (highest risk first)
    df = df.sort_values("score", ascending=False)

    return df


# Load data with caching (refresh every 30 seconds if auto_refresh is on)
@st.cache_data(ttl=30 if auto_refresh else 300)
def get_posts_cached():
    return load_data()


df_filtered = get_posts_cached()


# ════════════════════════════════════════════════════════════════════════════
# KEY METRICS (Top section)
# ════════════════════════════════════════════════════════════════════════════

st.header("📊 Key Metrics")

col1, col2, col3, col4 = st.columns(4)

# Total posts
with col1:
    total_posts = len(df_filtered)
    st.metric("Total Posts", total_posts)

# Critical posts
with col2:
    critical_count = len(df_filtered[df_filtered["score"] >= 80])
    st.metric("🔴 Critical Posts", critical_count)

# Average score
with col3:
    avg_score = df_filtered["score"].mean() if len(df_filtered) > 0 else 0
    st.metric("Average Score", f"{avg_score:.1f}/100")

# Escalated count
with col4:
    escalated_count = len(df_filtered[df_filtered["escalated"] == 1])
    st.metric("Actions Taken", escalated_count)


# ════════════════════════════════════════════════════════════════════════════
# CHARTS AND VISUALIZATIONS
# ════════════════════════════════════════════════════════════════════════════

st.header("📈 Analytics")

col1, col2 = st.columns(2)

# Category breakdown (simple table)
with col1:
    st.subheader("Posts by Category")
    if len(df_filtered) > 0:
        category_counts = df_filtered["category"].value_counts()
        for category, count in category_counts.items():
            st.write(f"**{category}:** {count} posts")
    else:
        st.info("No posts to display")

# Severity distribution (simple table)
with col2:
    st.subheader("Posts by Severity")
    if len(df_filtered) > 0:
        severity_counts = df_filtered["severity"].value_counts().sort_index(ascending=False)
        for severity, count in severity_counts.items():
            st.write(f"**Severity {int(severity)}/5:** {count} posts")
    else:
        st.info("No posts to display")


# ════════════════════════════════════════════════════════════════════════════
# RISK BREAKDOWN
# ════════════════════════════════════════════════════════════════════════════

st.header("⚠️ Risk Breakdown")

if len(df_filtered) > 0:
    col1, col2, col3, col4 = st.columns(4)

    critical = len(df_filtered[df_filtered["score"] >= 80])
    high = len(df_filtered[(df_filtered["score"] >= 60) & (df_filtered["score"] < 80)])
    moderate = len(df_filtered[(df_filtered["score"] >= 40) & (df_filtered["score"] < 60)])
    low = len(df_filtered[df_filtered["score"] < 40])

    with col1:
        st.metric("🔴 CRITICAL", critical)
    with col2:
        st.metric("🟠 HIGH", high)
    with col3:
        st.metric("🟡 MODERATE", moderate)
    with col4:
        st.metric("🟢 LOW", low)
else:
    st.info("No posts to analyze")


# ════════════════════════════════════════════════════════════════════════════
# COLLECTOR STATUS
# ════════════════════════════════════════════════════════════════════════════

st.header("🔄 Collector Status")

statuses = get_source_statuses()

if statuses:
    for status in statuses:
        source = status.get("source", "unknown")
        last_run = status.get("last_run_at", "Never")
        last_status = status.get("last_status", "unknown")
        posts_fetched = status.get("posts_fetched", 0)

        # Status indicator
        if last_status == "ok":
            status_emoji = "✅"
            status_color = "green"
        elif last_status == "mock":
            status_emoji = "📌"
            status_color = "blue"
        else:
            status_emoji = "❌"
            status_color = "red"

        col1, col2, col3 = st.columns([2, 3, 2])
        with col1:
            st.write(f"**{status_emoji} {source.upper()}**")
        with col2:
            st.write(f"Last run: {last_run[:16] if last_run else 'Never'}")
        with col3:
            st.write(f"Posts: {posts_fetched}")

else:
    st.info("No collector status data")


# ════════════════════════════════════════════════════════════════════════════
# POSTS TABLE (Main content)
# ════════════════════════════════════════════════════════════════════════════

st.header("📋 All Posts")

if len(df_filtered) > 0:
    # Display count
    st.subheader(f"Showing {len(df_filtered)} post(s)")

    # Create display DataFrame (select columns to show)
    display_df = df_filtered[
        [
            "id",
            "source",
            "title",
            "author",
            "category",
            "severity",
            "score",
            "risk_level",
            "upvotes",
            "comments",
            "escalated",
        ]
    ].copy()

    # Rename columns for display
    display_df.columns = [
        "ID",
        "Source",
        "Title",
        "Author",
        "Category",
        "Severity",
        "Score",
        "Risk Level",
        "Upvotes",
        "Comments",
        "Escalated",
    ]

    # Display table
    st.dataframe(
        display_df,
        width='stretch',
        hide_index=True,
        height=400,
    )

    # Detailed view (expandable for each post)
    st.subheader("📌 Detailed Post View")

    selected_post_id = st.selectbox(
        "Click to view full details:",
        df_filtered["id"].values,
        format_func=lambda x: f"Post #{x}: {df_filtered[df_filtered['id'] == x]['title'].values[0][:60]}...",
    )

    # Show selected post details
    selected_post = df_filtered[df_filtered["id"] == selected_post_id].iloc[0]

    col1, col2 = st.columns(2)

    with col1:
        st.write(f"**Title:** {selected_post['title']}")
        st.write(f"**Author:** {selected_post['author']}")
        st.write(f"**Source:** {selected_post['source']}")
        st.write(f"**Posted at:** {selected_post.get('posted_at', 'Unknown')[:16]}")

    with col2:
        st.write(f"**Category:** {selected_post['category']}")
        st.write(f"**Severity:** {selected_post['severity']}/5")
        st.write(f"**Score:** {selected_post['score']:.1f}/100")
        st.write(f"**Risk Level:** {selected_post['risk_level']}")

    st.write("**Full Content:**")
    st.text_area(
        "Post body:",
        value=selected_post.get("body", ""),
        height=150,
        disabled=True,
    )

    st.write("**Analysis:**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write(f"**Summary:** {selected_post.get('summary', 'N/A')}")
    with col2:
        st.write(f"**Engagement:** {selected_post['upvotes']} upvotes, {selected_post['comments']} comments")
    with col3:
        escalated = selected_post['escalated']
        status = "✅ Actions Taken" if escalated else "⏳ Pending"
        st.write(f"**Status:** {status}")
        if escalated:
            st.write(f"**Log:** {selected_post.get('actions_log', 'N/A')[:100]}...")

else:
    st.warning("No posts match your filters. Try adjusting the filters above.")


# ════════════════════════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════════════════════════

st.divider()
st.markdown(
    """
    **Zomato Social Listening System**
    - Module 2: Database storage
    - Module 3: Reddit collector
    - Module 5: Claude AI classifier
    - Module 6: Escalation scorer
    - Module 7: Action handler
    - Module 8: Dashboard (you are here)
    
    Last updated: """ + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
)
