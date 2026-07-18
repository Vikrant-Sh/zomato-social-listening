"""
collectors/scheduler.py — Module 9: Automatic Collector Scheduler

════════════════════════════════════════════════════════════════════════════
WHAT THIS MODULE DOES (in plain English)
════════════════════════════════════════════════════════════════════════════

Runs all data collectors (Reddit, Twitter, RSS) on automatic schedules.

HOW IT WORKS:
  1. Start an APScheduler background scheduler
  2. Schedule Reddit collector to run every 30 minutes
  3. Schedule Twitter collector to run every 1 hour
  4. Schedule RSS collector to run every 2 hours
  5. Log each run with timestamp and results
  6. Keep running until user stops it (Ctrl+C)

WHY SCHEDULING:
  - Real-time monitoring (not just manual runs)
  - Automatic updates to dashboard
  - Scales to production (just add more collectors)
  - Configurable intervals (adjust as needed)

EXAMPLE OUTPUT:
  [14:30:00] Starting Reddit collector...
  [14:30:05] ✅ Reddit: 3 new posts, 2 duplicates
  [14:30:05] Starting Twitter collector...
  [14:30:12] ✅ Twitter: 2 new tweets (mock)
  [15:00:00] Starting RSS collector...
  [15:00:08] ✅ RSS: 1 new entry
  [15:30:00] Starting Reddit collector...
  ... (repeats)
════════════════════════════════════════════════════════════════════════════
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Import all collectors
sys.path.insert(0, str(Path(__file__).parent.parent))
from collectors.reddit import collect_and_save as reddit_collect
from collectors.twitter import collect_and_save as twitter_collect
from collectors.rss import collect_and_save as rss_collect


# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION: Schedules for each collector
# ════════════════════════════════════════════════════════════════════════════

class SchedulerConfig:
    """
    Configure how often each collector runs.
    Times are in minutes.
    
    For demo/testing: 5 minutes gives fast updates
    For production: increase to 30-120 minutes to avoid rate limits
    """

    # Run Reddit collector every 5 minutes (demo speed)
    REDDIT_INTERVAL = 5

    # Run Twitter every 5 minutes (demo speed)
    TWITTER_INTERVAL = 5

    # Run RSS feeds every 5 minutes (demo speed)
    RSS_INTERVAL = 5


# ════════════════════════════════════════════════════════════════════════════
# COLLECTOR JOBS (What runs on schedule)
# ════════════════════════════════════════════════════════════════════════════


def reddit_job():
    """
    Scheduled job: Collect from Reddit.

    WHAT IT DOES:
    1. Call reddit_collect()
    2. Log results
    3. Return without waiting (background job)
    """
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{timestamp}] 🔄 Reddit collector running...")

    try:
        new, dups, errors, used_mock = reddit_collect()
        source = "MOCK" if used_mock else "LIVE"
        status = "✅" if not errors else "⚠️"
        print(
            f"[{timestamp}] {status} Reddit ({source}): {new} new, {dups} duplicates"
        )
        if errors:
            print(f"          Errors: {errors}")
    except Exception as e:
        print(f"[{timestamp}] ❌ Reddit error: {str(e)}")


def twitter_job():
    """
    Scheduled job: Collect from Twitter.

    WHAT IT DOES:
    1. Call twitter_collect()
    2. Log results
    3. Return without waiting (background job)
    """
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{timestamp}] 🔄 Twitter collector running...")

    try:
        new, dups, errors, used_mock = twitter_collect()
        source = "MOCK" if used_mock else "LIVE"
        status = "✅" if not errors else "⚠️"
        print(
            f"[{timestamp}] {status} Twitter ({source}): {new} new, {dups} duplicates"
        )
        if errors:
            print(f"          Errors: {errors}")
    except Exception as e:
        print(f"[{timestamp}] ❌ Twitter error: {str(e)}")


def rss_job():
    """
    Scheduled job: Collect from RSS feeds.

    WHAT IT DOES:
    1. Call rss_collect()
    2. Log results
    3. Return without waiting (background job)
    """
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{timestamp}] 🔄 RSS collector running...")

    try:
        new, dups, errors, used_mock = rss_collect()
        source = "MOCK" if used_mock else "LIVE"
        status = "✅" if not errors else "⚠️"
        print(
            f"[{timestamp}] {status} RSS ({source}): {new} new, {dups} duplicates"
        )
        if errors:
            print(f"          Errors: {errors}")
    except Exception as e:
        print(f"[{timestamp}] ❌ RSS error: {str(e)}")


# ════════════════════════════════════════════════════════════════════════════
# SCHEDULER SETUP
# ════════════════════════════════════════════════════════════════════════════


def start_scheduler():
    """
    Start the background scheduler.

    WHAT IT DOES:
    1. Create a BackgroundScheduler (runs in separate thread)
    2. Add jobs for each collector
    3. Start the scheduler
    4. Log startup message
    5. Return the scheduler (so you can stop it later)

    USAGE:
        scheduler = start_scheduler()
        # ... do other things ...
        scheduler.shutdown()  # Stop it when done
    """

    scheduler = BackgroundScheduler()

    # Add jobs with their intervals
    scheduler.add_job(
        reddit_job,
        trigger=IntervalTrigger(minutes=SchedulerConfig.REDDIT_INTERVAL),
        id="reddit_collector",
        name="Reddit Collector",
    )

    scheduler.add_job(
        twitter_job,
        trigger=IntervalTrigger(minutes=SchedulerConfig.TWITTER_INTERVAL),
        id="twitter_collector",
        name="Twitter Collector",
    )

    scheduler.add_job(
        rss_job,
        trigger=IntervalTrigger(minutes=SchedulerConfig.RSS_INTERVAL),
        id="rss_collector",
        name="RSS Collector",
    )

    # Start the scheduler
    scheduler.start()

    # Print startup info
    print("=" * 70)
    print("🚀 Zomato Social Listening Scheduler Started")
    print("=" * 70)
    print(f"📅 Schedule:")
    print(f"   - Reddit:  every {SchedulerConfig.REDDIT_INTERVAL} minutes")
    print(f"   - Twitter: every {SchedulerConfig.TWITTER_INTERVAL} minutes")
    print(f"   - RSS:     every {SchedulerConfig.RSS_INTERVAL} minutes")
    print(f"\n📊 Dashboard: http://localhost:8501")
    print(f"📝 Press Ctrl+C to stop\n")
    print("=" * 70)

    return scheduler


# ════════════════════════════════════════════════════════════════════════════
# MAIN: Run the scheduler
# ════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    try:
        scheduler = start_scheduler()

        # Keep running until user presses Ctrl+C
        while True:
            pass

    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping scheduler...")
        scheduler.shutdown()
        print("✅ Scheduler stopped")
