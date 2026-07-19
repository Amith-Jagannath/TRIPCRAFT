"""
TripCraft Streamlit UI.

Run with: streamlit run frontend/app.py
Requires the FastAPI backend running at localhost:8000 (see backend/main.py).
"""
import streamlit as st
import requests
from datetime import date, timedelta

API_URL = "http://localhost:8000"

st.set_page_config(page_title="TripCraft", page_icon="🧳", layout="wide")
st.title("🧳 TripCraft — Autonomous Travel Planning Agent")
st.caption("Multi-agent planner: planner → flight/hotel/weather workers → itinerary → budget critic (with replanning loop)")

if "plan" not in st.session_state:
    st.session_state.plan = None
if "user_id" not in st.session_state:
    st.session_state.user_id = "amith_demo"

with st.sidebar:
    st.header("Trip Details")
    origin = st.text_input("Origin city", "Bengaluru")
    destination = st.text_input("Destination city", "Tokyo")
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Start date", date.today() + timedelta(days=30))
    with col2:
        end = st.date_input("End date", date.today() + timedelta(days=35))
    budget = st.number_input("Budget (INR)", min_value=5000, value=80000, step=5000)
    travelers = st.number_input("Travelers", min_value=1, value=1)
    preferences = st.text_area("Preferences (optional)", "No early flights, prefer walkable areas")
    user_id = st.text_input("User ID (for memory)", st.session_state.user_id)

    plan_button = st.button("Plan my trip", type="primary", use_container_width=True)

if plan_button:
    with st.spinner("Agents are planning your trip — this can take 20-40s..."):
        try:
            resp = requests.post(f"{API_URL}/plan", json={
                "origin_city": origin,
                "destination_city": destination,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "budget_inr": budget,
                "travelers": travelers,
                "preferences": preferences,
                "user_id": user_id,
            }, timeout=120)
            resp.raise_for_status()
            st.session_state.plan = resp.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Couldn't reach the planning backend: {e}\n\nIs `uvicorn backend.main:app` running?")

plan = st.session_state.plan

if plan:
    budget_info = plan["budget"]
    status_color = "red" if budget_info["over_budget"] else "green"

    st.subheader("Budget Summary")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Flights", f"₹{budget_info['flights_inr']:,.0f}")
    b2.metric("Hotel", f"₹{budget_info['hotel_inr']:,.0f}")
    b3.metric("Activities", f"₹{budget_info['activities_inr']:,.0f}")
    b4.metric("Total", f"₹{budget_info['total_inr']:,.0f}",
              delta=f"{'Over' if budget_info['over_budget'] else 'Under'} by ₹{abs(budget_info['delta_inr']):,.0f}",
              delta_color="inverse" if budget_info["over_budget"] else "normal")

    if plan.get("selected_flight"):
        f = plan["selected_flight"]
        st.info(f"✈️ **Flight:** {f['airline']} — ₹{f['price_inr']:,.0f} ({f['stops']} stop(s))")
    if plan.get("selected_hotel"):
        h = plan["selected_hotel"]
        st.info(f"🏨 **Hotel:** {h['name']} — ₹{h['price_per_night_inr']:,.0f}/night, rating {h.get('rating', 'N/A')}")

    st.subheader("Day-by-Day Itinerary")
    for day in plan["days"]:
        with st.expander(f"Day {day['day_number']} — {day['date']} — {day['summary']}", expanded=False):
            if day.get("weather"):
                w = day["weather"]
                st.caption(f"🌤️ {w['condition']}, {w['temp_min_c']}°C–{w['temp_max_c']}°C")
            for act in day.get("activities", []):
                st.write(f"- {act}")
            st.caption(f"Estimated cost: ₹{day.get('estimated_cost_inr', 0):,.0f}")

            approved = st.checkbox("Approve this day", value=day.get("approved", False), key=f"approve_{day['day_number']}")

    st.subheader("Agent Reasoning Trace")
    st.caption("Every decision the agents made, in order — this is the transparency layer.")
    for line in plan.get("trace", []):
        st.text(line)

    st.divider()
    st.subheader("💾 Save a preference for next time")
    note = st.text_input("e.g. 'I hate long layovers' or 'I love hostels over hotels'")
    if st.button("Save preference"):
        if note:
            requests.post(f"{API_URL}/memory/{user_id}/note", params={"note": note})
            st.success("Saved — future trips for this user will factor this in.")
else:
    st.info("Fill in trip details in the sidebar and click **Plan my trip** to begin.")
