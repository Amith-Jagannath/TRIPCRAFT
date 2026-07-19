"""
Itinerary agent — takes the selected flight/hotel/weather and generates a
day-by-day activity plan. This is where the LLM does genuine planning work
(deciding what to do each day, adapting to weather).
"""
from __future__ import annotations
import json
import re

from backend.models import AgentState
from backend.agents.llm import call_llm


def itinerary_node(state: AgentState) -> AgentState:
    req = state.request
    plan = state.plan

    weather_summary = "\n".join(
        f"Day {d.day_number} ({d.date}): {d.weather.condition}, {d.weather.temp_min_c}-{d.weather.temp_max_c}C"
        if d.weather else f"Day {d.day_number} ({d.date}): weather unknown"
        for d in plan.days
    )
    memory_context = "\n".join(f"- {m}" for m in state.memory_notes) if state.memory_notes else "None"

    prompt = f"""Plan a {len(plan.days)}-day itinerary for a trip to {req.destination_city}.

Traveler preferences: {req.preferences or "None given"}
Remembered preferences: {memory_context}
Weather forecast:
{weather_summary}

Return ONLY valid JSON, no markdown formatting, no commentary, in this exact shape:
{{"days": [{{"day_number": 1, "summary": "short theme (max 6 words)", "activities": ["activity (max 8 words)", "activity 2", "activity 3"], "estimated_cost_inr": 2000}}]}}
Keep estimated_cost_inr realistic per-day for food + activities + local transport (not flights/hotel).
Adapt activities to the weather (e.g. indoor options on rainy days).
CRITICAL: output must be COMPACT - a single line, no indentation, no extra
spaces or line breaks between JSON tokens. Pretty-printed/indented JSON
wastes tokens and gets cut off before finishing - compact JSON avoids this.
Keep every text field short for the same reason."""

    # Scale the token budget to trip length, with extra headroom since even
    # with the compact-JSON instruction above, models sometimes ignore it.
    token_budget = 600 + (350 * len(plan.days))
    raw = call_llm(prompt, max_tokens=token_budget)

    # Keep a short preview of the raw output for debugging - if parsing
    # fails below, this gets added to the trace so it's visible in the UI
    # instead of us having to guess what the model actually returned.
    raw_preview = raw[:300].replace("\n", " ")

    # If the LLM call itself failed, llm.py wraps it as "[LLM call failed: ...]"
    # - catch that explicitly rather than letting it fall through to a
    # confusing JSON parse error.
    if raw.startswith("[LLM call failed:"):
        plan.trace.append(f"[ItineraryAgent] LLM call failed, days left unplanned. Detail: {raw_preview!r}")
        return state

    try:
        # Strip accidental markdown fences before parsing
        cleaned = re.sub(r"^```json\s*|\s*```$", "", raw.strip())
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Likely truncated mid-string (hit token limit) - try salvaging
        # whichever complete day objects came through before the cutoff,
        # rather than throwing away the entire response.
        try:
            repaired = _repair_truncated_json(cleaned)
            parsed = json.loads(repaired)
            plan.trace.append("[ItineraryAgent] Response was truncated - salvaged partial itinerary.")
        except Exception as e:
            plan.trace.append(
                f"[ItineraryAgent] Failed to parse LLM output ({e}); days left unplanned. "
                f"Raw output preview: {raw_preview!r}"
            )
            return state

    try:
        for day_data in parsed.get("days", []):
            idx = day_data["day_number"] - 1
            if 0 <= idx < len(plan.days):
                plan.days[idx].summary = day_data.get("summary", plan.days[idx].summary)
                plan.days[idx].activities = day_data.get("activities", [])
                plan.days[idx].estimated_cost_inr = day_data.get("estimated_cost_inr", 0)
        if "[ItineraryAgent] Response was truncated" not in (plan.trace[-1] if plan.trace else ""):
            plan.trace.append("[ItineraryAgent] Generated day-by-day plan.")
    except (KeyError, TypeError) as e:
        plan.trace.append(f"[ItineraryAgent] Parsed JSON but couldn't apply it ({e}); days left unplanned.")

    return state


def _repair_truncated_json(cleaned: str) -> str:
    """Best-effort repair for JSON cut off mid-generation. Finds the last
    complete '}' that closes a day object inside the 'days' array and closes
    the array/object around it, discarding whatever partial day came after."""
    last_complete_day_end = cleaned.rfind("},")
    if last_complete_day_end == -1:
        last_complete_day_end = cleaned.rfind("}")
    if last_complete_day_end == -1:
        raise ValueError("No complete day object found to salvage")
    truncated = cleaned[:last_complete_day_end + 1]
    return truncated + "]}"