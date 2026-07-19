"""
The agent graph. This is the centerpiece of the "agentic" architecture:

    planner -> [flight_worker, hotel_worker, weather_worker] -> itinerary
        -> budget_critic --(over budget, iterations left)--> hotel_worker (loop)
                          --(within budget OR out of iterations)--> human_approval (END)

LangGraph's StateGraph makes this loop explicit and inspectable - you can
literally draw the graph and point to the reflection edge in an interview.
"""
from __future__ import annotations
from langgraph.graph import StateGraph, END

from backend.models import AgentState
from backend.agents.planner import planner_node
from backend.agents.workers import flight_worker_node, hotel_worker_node, weather_worker_node
from backend.agents.itinerary import itinerary_node
from backend.agents.budget_critic import budget_critic_node


def _route_after_critic(state: AgentState) -> str:
    """Conditional edge: decide whether to loop back and replan, or stop."""
    if state.plan.status == "replanning":
        return "hotel_worker"  # re-fetch hotels under the new (implicit) cap
    return "end"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("flight_worker", flight_worker_node)
    graph.add_node("hotel_worker", hotel_worker_node)
    graph.add_node("weather_worker", weather_worker_node)
    graph.add_node("itinerary", itinerary_node)
    graph.add_node("budget_critic", budget_critic_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "flight_worker")
    graph.add_edge("flight_worker", "hotel_worker")
    graph.add_edge("hotel_worker", "weather_worker")
    graph.add_edge("weather_worker", "itinerary")
    graph.add_edge("itinerary", "budget_critic")

    graph.add_conditional_edges(
        "budget_critic",
        _route_after_critic,
        {"hotel_worker": "hotel_worker", "end": END},
    )

    return graph.compile()


# Compiled once at import time and reused across requests.
trip_graph = build_graph()


def run_trip_planning(request) -> AgentState:
    from backend.models import TripPlan
    initial_state = AgentState(request=request, plan=TripPlan(request=request))
    result = trip_graph.invoke(initial_state)
    # langgraph returns a dict-like object matching the state schema
    return AgentState(**result) if isinstance(result, dict) else result
