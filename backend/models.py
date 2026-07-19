"""
Shared data models for TripCraft.
These define the shape of state that flows through the LangGraph agent graph,
and the request/response schemas for the FastAPI layer.
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import date


# ---------- User input ----------

class TripRequest(BaseModel):
    origin_city: str = Field(..., description="City/airport the trip starts from, e.g. 'Bengaluru'")
    destination_city: str = Field(..., description="Destination city, e.g. 'Tokyo'")
    start_date: date
    end_date: date
    budget_inr: float = Field(..., description="Total trip budget in INR")
    travelers: int = 1
    preferences: Optional[str] = Field(
        None, description="Free-text preferences, e.g. 'no early flights, walkable areas'"
    )
    user_id: str = Field(default="default_user", description="Used to scope long-term memory")


# ---------- Tool outputs ----------

class FlightOption(BaseModel):
    airline: str
    flight_number: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    price_inr: float
    stops: int = 0
    raw: Optional[Dict[str, Any]] = None  # original API payload, kept for debugging/tracing


class HotelOption(BaseModel):
    name: str
    area: Optional[str] = None
    price_per_night_inr: float
    rating: Optional[float] = None
    distance_to_center_km: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None


class WeatherDay(BaseModel):
    date: date
    condition: str
    temp_min_c: float
    temp_max_c: float


# ---------- Itinerary ----------

class DayPlan(BaseModel):
    day_number: int
    date: date
    summary: str
    activities: List[str] = Field(default_factory=list)
    estimated_cost_inr: float = 0
    weather: Optional[WeatherDay] = None
    approved: bool = False  # human-in-the-loop gate


class BudgetBreakdown(BaseModel):
    flights_inr: float = 0
    hotel_inr: float = 0
    activities_inr: float = 0
    buffer_inr: float = 0
    total_inr: float = 0
    over_budget: bool = False
    delta_inr: float = 0  # positive = over budget, negative = under budget


class TripPlan(BaseModel):
    request: TripRequest
    selected_flight: Optional[FlightOption] = None
    selected_hotel: Optional[HotelOption] = None
    days: List[DayPlan] = Field(default_factory=list)
    budget: BudgetBreakdown = Field(default_factory=BudgetBreakdown)
    status: Literal["planning", "awaiting_approval", "replanning", "approved", "final"] = "planning"
    trace: List[str] = Field(default_factory=list)  # human-readable agent decision log


# ---------- Agent graph state ----------

class AgentState(BaseModel):
    """The single object passed between every node in the LangGraph graph."""
    request: TripRequest
    plan: TripPlan
    flight_candidates: List[FlightOption] = Field(default_factory=list)
    hotel_candidates: List[HotelOption] = Field(default_factory=list)
    weather_forecast: List[WeatherDay] = Field(default_factory=list)
    memory_notes: List[str] = Field(default_factory=list)  # retrieved long-term memory
    iteration: int = 0
    max_iterations: int = 3
    needs_human_approval: bool = False
    human_feedback: Optional[str] = None
    error: Optional[str] = None
