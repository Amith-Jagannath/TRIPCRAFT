"""
Planner agent.

Responsibilities:
1. Pull relevant long-term memory for this user (past preferences).
2. Produce a short natural-language plan of sub-tasks (logged into the trace
   so the user/interviewer can see the agent's reasoning).
3. Set up the initial TripPlan skeleton with day placeholders.

This node does NOT call the LLM for every mechanical step - only where
judgment is actually needed (interpreting preferences). Fetching flights/
hotels/weather is deterministic tool-calling handled by worker nodes.
"""
from __future__ import annotations
from datetime import timedelta

from backend.models import AgentState, DayPlan
from backend.tools import memory
from backend.agents.llm import call_llm


def planner_node(state: AgentState) -> AgentState:
    req = state.request

    # 1. Retrieve long-term memory relevant to this trip
    query = f"trip to {req.destination_city}"
    remembered = memory.get_relevant_preferences(req.user_id, query)
    state.memory_notes = remembered

    # 2. Ask the LLM to translate free-text preferences + memory into a short
    #    structured planning note. This is the one place in the planner where
    #    judgment matters more than deterministic logic.
    memory_context = "\n".join(f"- {m}" for m in remembered) if remembered else "None yet."
    prompt = f"""You are a travel planning assistant. A user wants to plan a trip.

Destination: {req.destination_city}
From: {req.origin_city}
Dates: {req.start_date} to {req.end_date}
Budget: INR {req.budget_inr}
Stated preferences: {req.preferences or "None given"}
Remembered preferences from past trips:
{memory_context}

In 2-3 short sentences, summarize the planning approach you'll take
(e.g. what to prioritize, any constraints to respect). Do not list flights
or hotels yet - just the strategy."""

    strategy = call_llm(prompt)
    state.plan.trace.append(f"[Planner] {strategy}")

    # 3. Set up empty day placeholders (workers/critic will fill these in)
    num_days = (req.end_date - req.start_date).days + 1
    state.plan.days = [
        DayPlan(
            day_number=i + 1,
            date=req.start_date + timedelta(days=i),
            summary="Not yet planned",
        )
        for i in range(num_days)
    ]
    state.plan.status = "planning"
    return state
