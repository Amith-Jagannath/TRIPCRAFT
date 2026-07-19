# TripCraft — Autonomous Travel Planning Agent

A multi-agent system that plans a trip end-to-end: flights, hotels,
weather-aware day-by-day itinerary, and budget-constrained replanning —
with a human-in-the-loop approval step and long-term memory of your
preferences across sessions.

## Why this project exists

Built to demonstrate real agentic AI engineering patterns beyond a basic
"RAG chatbot": planning/task decomposition, multi-agent orchestration,
real tool use (live APIs, not toy examples), a genuine reflection loop
(budget critic re-triggers hotel search on constraint violation), long-term
memory, and human approval gates.

## Architecture

```
planner ──▶ flight_worker ──▶ hotel_worker ──▶ weather_worker ──▶ itinerary ──▶ budget_critic
                                    ▲                                                │
                                    └──────────────── replan if over budget ─────────┘
                                                              │
                                                    (within budget) ──▶ human approval (Streamlit UI)
```

Built with **LangGraph**, which makes this loop an explicit, inspectable
state graph rather than hidden control flow.

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph | Explicit state graph, easy to draw/explain |
| LLM | Gemini (free tier), swappable to Claude/Cohere | `backend/agents/llm.py` — one config line to swap |
| Flights + Hotels | Booking.com API via RapidAPI | Real, self-serve, free-tier signup |
| Weather | Open-Meteo | Free, keyless |
| Currency | Frankfurter | Free, keyless |
| Memory | ChromaDB (local, persistent) | Semantic search over past preferences |
| Backend | FastAPI | `/plan` endpoint runs the full agent graph |
| Frontend | Streamlit | Approval UI + reasoning trace viewer |

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env and fill in:
#   GEMINI_API_KEY      (aistudio.google.com/apikey)
#   RAPIDAPI_KEY        (rapidapi.com -> Booking.com API)

# 3. Run the backend (terminal 1)
uvicorn backend.main:app --reload --port 8000

# 4. Run the frontend (terminal 2)
streamlit run frontend/app.py
```

Then open the Streamlit URL it prints (usually http://localhost:8501).

## Known rough edges (be upfront about these in interviews - it shows maturity)

- **RapidAPI response shapes drift.** The Booking.com listing on RapidAPI has
  changed field names before. If `search_flights`/`search_hotels` return
  empty lists, hit the endpoint once in RapidAPI's "Test Endpoint" playground
  and compare the real JSON shape to `backend/tools/booking_com.py`'s parsing
  logic — it's written defensively (try/except per-item) for exactly this
  reason, but the field names may need a one-line update.
- **Weather only covers ~16 days out.** Open-Meteo's free forecast has a
  real horizon limit; trips planned further ahead will show "weather
  unknown" rather than a guess. This is intentional — better to be honest
  about missing data than fabricate a forecast.
- **Budget critic's replanning is a heuristic, not another LLM call.** This
  is deliberate: arithmetic-based decisions (biggest cost lever) should be
  deterministic and auditable, not subject to LLM variance.

## Next steps / extension ideas

- Add a maps/distance tool (OpenRouteService) to sanity-check that daily
  activities aren't geographically scattered
- Add an MCP server wrapper so this can be invoked as a tool from Claude
  Desktop or other MCP clients
- Persist full trip history (not just preference notes) for "show me what
  changed since last time" diffing
