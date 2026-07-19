"""
Budget critic agent — the reflection loop.

Checks the running total against the user's budget. If over budget, it
doesn't just reject the plan silently: it decides WHAT to cut (cheaper
hotel? fewer paid activities?) and flags the graph to loop back through
the relevant worker again. This is the "replan on constraint violation"
pattern that's the whole point of an agentic (vs single-shot) system.
"""
from __future__ import annotations

from backend.models import AgentState, BudgetBreakdown


def budget_critic_node(state: AgentState) -> AgentState:
    req = state.request
    plan = state.plan
    nights = max((req.end_date - req.start_date).days, 1)

    flights_cost = plan.selected_flight.price_inr if plan.selected_flight else 0
    hotel_cost = (plan.selected_hotel.price_per_night_inr * nights) if plan.selected_hotel else 0
    activities_cost = sum(d.estimated_cost_inr for d in plan.days)
    buffer = 0.1 * req.budget_inr  # always reserve 10% buffer for misc/emergencies

    total = flights_cost + hotel_cost + activities_cost + buffer
    delta = total - req.budget_inr

    plan.budget = BudgetBreakdown(
        flights_inr=flights_cost,
        hotel_inr=hotel_cost,
        activities_inr=activities_cost,
        buffer_inr=buffer,
        total_inr=total,
        over_budget=delta > 0,
        delta_inr=round(delta, 2),
    )

    if delta > 0 and state.iteration < state.max_iterations:
        # Decide what to cut. Simple, explainable heuristic (not another LLM
        # call - the critic's job is deterministic, checkable arithmetic,
        # which is exactly why a human should trust this step).
        if hotel_cost > flights_cost and hotel_cost > activities_cost:
            reason = "hotel cost is the largest lever - retry hotel search with a lower cap"
            state.needs_human_approval = False
            plan.status = "replanning"
        elif activities_cost > flights_cost:
            reason = "trimming daily activity budget"
            # Simple proportional trim rather than another API round-trip
            scale = max(0.5, req.budget_inr * 0.5 / max(activities_cost, 1))
            for d in plan.days:
                d.estimated_cost_inr = round(d.estimated_cost_inr * scale, 2)
            plan.status = "planning"
        else:
            reason = "flights are the largest cost and can't be easily re-optimized automatically"
            plan.status = "awaiting_approval"
            state.needs_human_approval = True

        plan.trace.append(
            f"[BudgetCritic] Over budget by INR {delta:,.0f}. Reason: {reason}. "
            f"(iteration {state.iteration + 1}/{state.max_iterations})"
        )
        state.iteration += 1
    else:
        plan.status = "awaiting_approval"
        state.needs_human_approval = True
        if delta > 0:
            plan.trace.append(
                f"[BudgetCritic] Still over budget by INR {delta:,.0f} after "
                f"{state.max_iterations} attempts - escalating to human for approval/override."
            )
        else:
            plan.trace.append(f"[BudgetCritic] Within budget (INR {-delta:,.0f} to spare). Ready for review.")

    return state
