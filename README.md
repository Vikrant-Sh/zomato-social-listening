# 🔭 Zomato Social Watch

A real-time social listening & escalation tool built for the Zomato
AI-Native Intern assignment.

Every 5 minutes it pulls live posts mentioning Zomato from **Reddit,
X/Twitter, and Google News**, filters the noise for free, asks
**Claude** to classify and judge what's left, computes an explainable
escalation score, and fires **real actions** (Slack alert + ClickUp
ticket) for anything that crosses the line — all visible on a live
dashboard.

## Architecture

```
Scheduler (5 min)
   → Collectors (Reddit / X / RSS)
   → Normalize + Dedupe (SQLite primary key)
   → Pre-filter (keywords + VADER — kills ~60% for free)
   → Claude Haiku (category · severity · summary, batched)
   → Scorer (severity 50 + engagement 30 + recency 20; safety floor = 70)
   → Action Router (fires ONCE per post: Slack + ClickUp)
   → SQLite → Streamlit dashboard
```

## Setup (10 minutes)

1. **Clone & enter the project**
   ```bash
   git clone <repo-url>
   cd zomato-social-watch
   ```

2. **Create a virtual environment** (a private toybox for dependencies)
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Mac/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Add your secrets**
   ```bash
   # copy the template, then edit .env with your real keys
   cp .env.example .env
   ```
   You need: an Anthropic API key, a Slack
   Incoming Webhook URL, and a ClickUp API token + List ID.
   (`.env.example` has links for each.)

5. **Check everything is wired**
   ```bash
   python config.py
   ```
   You should see `✅ All secrets loaded.`

6. **Run it**
   ```bash
   streamlit run app.py
   ```
   The dashboard opens at http://localhost:8501 and the pipeline
   starts automatically, refreshing every 5 minutes.

## Project structure

```
app.py            # dashboard + scheduler (the only file you run)
config.py         # ALL settings & secrets loading
runner.py         # one full pipeline cycle
collectors/       # reddit / x / rss  →  normalized posts
pipeline/         # prefilter → classifier (Claude) → scorer
actions/          # slack + clickup, behind one fire-once router
database/         # db.py (all SQL) + socialwatch.db (auto-created)
SCORING_NOTE.md   # categories, rubric, deliberate exclusions
```

## Status

- [x] Module 1 — project setup
- [ ] Module 2 — database
- [ ] Module 3 — Reddit collector
- [ ] Module 4 — pre-filter
- [ ] Module 5 — Claude classifier
- [ ] Module 6 — scorer
- [ ] Module 7 — actions (Slack + ClickUp)
- [ ] Module 8 — runner
- [ ] Module 9 — dashboard
- [ ] Module 10 — X + RSS collectors
