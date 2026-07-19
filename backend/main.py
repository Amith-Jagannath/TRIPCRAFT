"""
FastAPI backend for TripCraft.

Run with: uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()  # must run before any tool/agent module reads os.getenv at import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.models import TripRequest, TripPlan
from backend.agents.graph import run_trip_planning
from backend.tools import memory

app = FastAPI(title="TripCraft API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for a local personal-project demo; tighten before any real deploy
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/plan", response_model=TripPlan)
def plan_trip(request: TripRequest) -> TripPlan:
    if request.end_date <= request.start_date:
        raise HTTPException(400, "end_date must be after start_date")
    try:
        final_state = run_trip_planning(request)
    except Exception as e:
        raise HTTPException(500, f"Planning failed: {e}")
    return final_state.plan


@app.post("/memory/{user_id}/note")
def add_memory_note(user_id: str, note: str):
    memory.add_preference(user_id, note)
    return {"status": "saved"}


@app.get("/memory/{user_id}")
def get_memory(user_id: str):
    return {"preferences": memory.list_all_preferences(user_id)}


@app.get("/health")
def health():
    return {"status": "ok"}
