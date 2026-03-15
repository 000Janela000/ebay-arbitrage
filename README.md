# eBay Arbitrage Analyzer

Monitor eBay USA auctions, compare their projected landed cost in Georgia (including $9/kg shipping) against Georgian marketplace prices, and rank every active auction from best to worst profit opportunity.

---

## Features

- **Category Profitability Analyzer** — scan all product categories to find the most profitable before committing to deep analysis
- **Live Auction Dashboard** — real-time table of active auctions sorted by composite opportunity score
- **Ending Soon Tab** — auctions grouped into time buckets (< 30 min, 30 m–1 h, 1–2 h, 2–6 h) so you know exactly what needs a bid decision right now
- **Automatic Price Estimation** — uses eBay BIN listings with noise-filtered queries to project final auction prices
- **Georgian Market Scrapers** - currently pulls live prices from mymarket.ge and extra.ge (disabled sources are skipped automatically)
- **Composite Scoring** - weighs margin, urgency, demand, confidence, and competition into a 0-100 score
- **VAT, Shipping & Selling Fees** - configurable landed-cost + net-revenue model
- **Weight Override** — manually set item weight to recalculate scores
- **eBay Quota Tracking** — warns when approaching the 5,000/day free API limit

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- An eBay Developer account (free) with Production API keys

---

## Database

The app uses **SQLite** — no database server required. On first startup, `ebay_arbitrage.db` is created automatically in the project root. No migrations to run, no Docker needed.

```
ebay-arbitrage/
└── ebay_arbitrage.db   ← auto-created on first uvicorn start
```

The default connection string in `.env.example` is correct and ready to use:

```
DATABASE_URL=sqlite+aiosqlite:///./ebay_arbitrage.db
```

---

## Setup

### 1. Get eBay API Keys

1. Go to [developer.ebay.com](https://developer.ebay.com)
2. Sign in with your eBay account and accept the API License Agreement
3. Navigate to **My Account → Application Keys**
4. Click **Get a Production Key**, give it any name
5. Copy your **App ID (Client ID)** and **Cert ID (Client Secret)**

### 2. Backend

```bash
# From the project root
cd C:\...\ebay-arbitrage

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Linux/Mac: source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (needed for veli.store scraping)
playwright install chromium

# Copy environment file (credentials can also be entered via the UI)
copy .env.example .env

# Start the backend (creates ebay_arbitrage.db automatically on first run)
uvicorn backend.main:app --reload --port 8000
```

Confirm it's running: `http://localhost:8000/health` → `{"ok": true}`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## First-Run Wizard

If no eBay credentials are configured, the app shows a **Setup Wizard** that walks you through registering and entering your API keys.

Alternatively, open **Settings** (gear icon, top right) at any time:

1. Paste your eBay **Client ID** and **Client Secret**
2. Click **Validate Credentials** — should show a green checkmark
3. Adjust shipping rate, VAT toggle, and weight defaults as needed
4. Click **Save Settings**

---

## Usage Guide

### Step 1: Analyze Categories

Navigate to **Categories** and click **Analyze All**.

This samples eBay BIN prices and Georgian marketplace prices for each product category to estimate which categories have the highest profit margins. Takes a few minutes and uses ~24 eBay API calls. Results are cached in the database.

### Step 2: Pick Your Category

Click any category card. The card shows:
- Estimated average profit margin
- Default item weight (used for shipping cost)
- Number of active auctions currently in the DB

High-margin categories (electronics, collectibles) appear first.

### Step 3: Refresh Data

Click **Refresh** on the Auction Dashboard. This:

1. Fetches active eBay auctions ending within 48 h in the selected category
2. Estimates final auction prices using eBay BIN listings (noise words stripped from queries for better matches)
3. Scrapes Georgian marketplace prices (active sources) with a 30-second timeout per item
4. Calculates landed cost (item + shipping at $9/kg + optional VAT) and net revenue (after optional selling fees)
5. Scores and ranks all opportunities on a 0–100 scale

A progress bar shows scraper status per platform.

### Step 4: Browse Opportunities (All Opportunities tab)

| Visual cue | Meaning |
|---|---|
| Green row | Profit ≥ 30% |
| Yellow row | Profit 15–30% |
| Red row | Profit < 15% |
| Orange badge | Ends in < 6 h |
| Red pulsing badge | Ends in < 2 h — act fast |

Click any row to open the **Detail Modal**, which shows:
- Full cost breakdown (bid + shipping + VAT → landed cost)
- Georgian listings with similarity scores
- Score breakdown (margin / urgency / demand / confidence / competition)
- Confidence adjusted for seller feedback and number of Georgian comparables

Use **Filter Bar** to narrow by category, minimum profit %, maximum bid, or whether Georgian price data exists.

### Step 5: Ending Soon tab

Switch to the **Ending Soon** tab to see a prioritized view of auctions closing in the next 6 hours, grouped into four urgency buckets:

| Bucket | Color |
|---|---|
| Ends in < 30 min | 🔴 Red — bid now or miss it |
| Ends in 30 min – 1 h | 🟠 Orange |
| Ends in 1 – 2 h | 🟡 Yellow |
| Ends in 2 – 6 h | ⚪ Gray |

Within each bucket items are sorted by opportunity score (highest first). Click any item to open the full detail modal.

### Step 6: Weight Overrides

If you know an item's actual weight (e.g. from the listing description), open the detail modal and enter it in the weight field. The opportunity score recalculates immediately using the corrected shipping cost.

---

## Opportunity Score Formula

```
score (0-100) = (margin_score x 0.35) + (urgency_score x 0.20)
              + (demand_score x 0.20) + (confidence_score x 0.15)
              + (competition_score x 0.10)
```

| Sub-score | How it's calculated |
|---|---|
| **margin_score** | Logistic sigmoid centered at 30% profit margin |
| **urgency_score** | Log-scale decay - 0.1 at >48 h, 1.0 at <30 min |
| **demand_score** | Listing/view/order signals from Georgian comparables |
| **confidence_score** | From price estimator (0.20–0.95), then adjusted (see below) |
| **competition_score** | `exp(−0.15 × bid_count)` |

### Confidence Adjustments

**Seller feedback (G1)**

| Feedback % | Multiplier |
|---|---|
| ≥ 98% | ×1.00 (no penalty) |
| 90–97% | ×0.85–0.99 (linear) |
| < 90% | ×0.75 |
| Unknown | ×0.95 |

**Georgian data richness (G2)**

| Listings found | Multiplier |
|---|---|
| 0 | ×0.70 — no comparables, highly uncertain |
| 1 | ×0.85 — single data point |
| 2 | ×0.95 — getting reliable |
| 3+ | ×1.00 — solid median |

---

## Architecture

```
backend/
├── main.py                   # FastAPI app + lifespan (creates DB, seeds settings)
├── config.py                 # pydantic-settings (reads .env)
├── database.py               # Async SQLAlchemy + SQLite
├── models.py                 # ORM models
├── routers/
│   ├── auctions.py           # /api/auctions — refresh, list, detail, weight override
│   ├── opportunities.py      # /api/opportunities — filtered/sorted opportunity list
│   └── categories.py         # /api/categories — analyze, status
└── services/
    ├── ebay_client.py         # OAuth2 + Browse API
    ├── currency_service.py    # NBG GEL/USD exchange rate
    ├── price_estimator.py     # BIN-based auction price prediction
    ├── opportunity_scorer.py  # Composite 0–100 scoring + confidence adjustments
    └── scraper_orchestrator.py # Runs all three scrapers with 30 s timeout

frontend/
└── src/
    ├── App.tsx
    ├── api/                   # Axios client + React Query hooks
    ├── pages/
    │   ├── CategoryAnalyzer.tsx
    │   └── AuctionDashboard.tsx  # Tab bar: All Opportunities / Ending Soon
    └── components/
        ├── OpportunityTable.tsx
        ├── UpcomingEndingsSection.tsx  # G4 — time-bucket view
        ├── AuctionDetailModal.tsx
        ├── FilterBar.tsx
        └── SettingsPanel.tsx
```

---

## API Reference

```
GET  /health
GET  /api/settings
PUT  /api/settings
POST /api/settings/validate-ebay
GET  /api/settings/currency-rate

GET  /api/categories
POST /api/categories/analyze
GET  /api/categories/analyze/status?job_id=

GET  /api/auctions?category_id=&sort_by=&order=&min_profit_pct=&max_bid_usd=&has_georgian_data=
POST /api/auctions/refresh
GET  /api/auctions/refresh/status?job_id=
GET  /api/auctions/{ebay_item_id}
PUT  /api/auctions/{ebay_item_id}/weight
POST /api/auctions/{ebay_item_id}/rescore

GET  /api/opportunities?sort_by=&order=&min_profit_pct=&has_georgian_data=
```

---

## Limitations

- **eBay API**: 5,000 calls/day on the free tier. The app caches BIN lookups to reduce repeated calls.
- **Georgian scrapers**: Site structure changes may require selector updates. Each query times out after 30 seconds so a stuck scraper never blocks a full refresh.
- **Disabled sources**: Some platforms may be disabled in the current runtime environment and are skipped automatically.
- **Price matching**: Georgian listing similarity is keyword-based. Low-confidence matches (score < 0.3) are excluded from scoring and confidence.
- **Exchange rate**: Fetched live from the National Bank of Georgia. If unavailable, GEL→USD conversions are skipped (no hardcoded fallback rate).

