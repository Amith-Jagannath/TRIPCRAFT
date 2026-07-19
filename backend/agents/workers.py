"""
Worker agent nodes — these do real tool calls (no LLM needed, pure
deterministic API calls) to fetch flight, hotel, and weather options.
"""
from __future__ import annotations

from backend.models import AgentState
from backend.tools import booking_com, weather


def flight_worker_node(state: AgentState) -> AgentState:
    req = state.request
    try:
        candidates = booking_com.search_flights(
            origin_city=req.origin_city,
            destination_city=req.destination_city,
            depart_date=req.start_date,
            return_date=req.end_date,
            adults=req.travelers,
        )
        state.flight_candidates = candidates
        cheapest = min(candidates, key=lambda f: f.price_inr) if candidates else None
        if cheapest:
            state.plan.selected_flight = cheapest
            state.plan.trace.append(
                f"[FlightWorker] Found {len(candidates)} options. "
                f"Selected cheapest: {cheapest.airline} at INR {cheapest.price_inr}."
            )
        else:
            state.plan.trace.append("[FlightWorker] No flight options found.")
    except Exception as e:
        state.error = f"Flight search failed: {e}"
        state.plan.trace.append(f"[FlightWorker] ERROR: {e}")
    return state


def hotel_worker_node(state: AgentState) -> AgentState:
    req = state.request
    try:
        candidates = booking_com.search_hotels(
            destination_city=req.destination_city,
            checkin=req.start_date,
            checkout=req.end_date,
            adults=req.travelers,
        )
        state.hotel_candidates = candidates
        # Prefer highest-rated hotel under a reasonable per-night cap rather
        # than just cheapest - pure lowest-price hotels are often unusable.
        nights = max((req.end_date - req.start_date).days, 1)
        affordable = [h for h in candidates if h.price_per_night_inr * nights <= req.budget_inr * 0.4]
        pool = affordable or candidates
        best = max(pool, key=lambda h: (h.rating or 0)) if pool else None
        if best:
            state.plan.selected_hotel = best
            state.plan.trace.append(
                f"[HotelWorker] Found {len(candidates)} options. "
                f"Selected: {best.name} (rating {best.rating}) at INR {best.price_per_night_inr}/night."
            )
        else:
            state.plan.trace.append("[HotelWorker] No hotel options found.")
    except Exception as e:
        state.error = f"Hotel search failed: {e}"
        state.plan.trace.append(f"[HotelWorker] ERROR: {e}")
    return state


def weather_worker_node(state: AgentState) -> AgentState:
    req = state.request
    try:
        forecast = weather.get_forecast(req.destination_city, req.start_date, req.end_date)
        state.weather_forecast = forecast
        by_date = {w.date: w for w in forecast}
        for day in state.plan.days:
            if day.date in by_date:
                day.weather = by_date[day.date]
        if forecast:
            state.plan.trace.append(f"[WeatherWorker] Retrieved {len(forecast)}-day forecast.")
        else:
            state.plan.trace.append("[WeatherWorker] Forecast unavailable (trip too far out or city not found).")
    except Exception as e:
        # Weather is non-critical - never block planning on it.
        state.plan.trace.append(f"[WeatherWorker] Skipped due to error: {e}")
    return state
