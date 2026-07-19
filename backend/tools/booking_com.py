"""
Wrapper around the Sky-scrapper API on RapidAPI (flights + hotels).
Confirmed real host (2026-07): sky-scrapper.p.rapidapi.com

Note: endpoint versions matter here - e.g. searchFlights has a "Version 1
(Deprecated)" and a "Version 2" listing with different behavior. Always
check which version's Code Snippets panel you're copying from RapidAPI's
playground before trusting a path/param here.
"""
from __future__ import annotations
import os
import requests
from typing import List, Dict, Any, Optional
from datetime import date

from backend.models import FlightOption, HotelOption

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "sky-scrapper.p.rapidapi.com")
BASE_HOST_URL = f"https://{RAPIDAPI_HOST}"

_HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
    "Content-Type": "application/json",
}


class BookingAPIError(Exception):
    pass


def _get(path: str, params: Dict[str, Any], version: str = "v1") -> Dict[str, Any]:
    """path should start with /flights/... or /hotels/..., NOT include /api/vX.
    version defaults to v1, but pass version='v2' for endpoints confirmed to
    live under /api/v2 (e.g. searchFlights, which has a deprecated v1 and a
    current v2 with different/better behavior)."""
    if not RAPIDAPI_KEY:
        raise BookingAPIError("RAPIDAPI_KEY not set. Fill in your .env file.")
    url = f"{BASE_HOST_URL}/api/{version}{path}"
    resp = requests.get(url, headers=_HEADERS, params=params, timeout=20)
    if resp.status_code != 200:
        raise BookingAPIError(f"{path} (v{version}) failed [{resp.status_code}]: {resp.text[:300]}")
    return resp.json()


# ---------- Location resolution ----------
# Confirmed real response shape (2026-07) from "Search Airport" under Flights:
#
# data[i].presentation.title / suggestionTitle / subtitle
# data[i].navigation.entityId
# data[i].navigation.entityType            "AIRPORT" or "CITY"
# data[i].navigation.relevantFlightParams.skyId       -> use for flight origin/destination
# data[i].navigation.relevantFlightParams.entityId    -> use alongside skyId
#
# Hotels use a SEPARATE endpoint (/hotels/searchDestinationOrHotel) with a
# flatter response shape - see resolve_hotel_location below.

from pydantic import BaseModel as _BaseModel


class FlightLocation(_BaseModel):
    sky_id: str
    entity_id: str


class HotelLocation(_BaseModel):
    entity_id: str


def search_airport(query: str) -> List[Dict[str, Any]]:
    """Raw results from the Search Airport endpoint, best match first."""
    data = _get("/flights/searchAirport", {"query": query, "locale": "en-US"})
    return data.get("data", [])


def resolve_flight_location(city_or_airport: str) -> Optional[FlightLocation]:
    results = search_airport(city_or_airport)
    for entry in results:
        params = entry.get("navigation", {}).get("relevantFlightParams")
        if params and params.get("skyId") and params.get("entityId"):
            return FlightLocation(sky_id=params["skyId"], entity_id=params["entityId"])
    return None


def resolve_hotel_location(city: str) -> Optional[HotelLocation]:
    """Confirmed real shape (2026-07) from /hotels/searchDestinationOrHotel:
    a flat list where each entry has entityId + entityType ('city', 'airport',
    'hotel', 'Train Station', etc). We want the first 'city' match - picking
    a 'hotel' or 'airport' entityId here would search the wrong scope."""
    data = _get("/hotels/searchDestinationOrHotel", {"query": city})
    results = data.get("data", [])
    for entry in results:
        if entry.get("entityType", "").lower() == "city":
            return HotelLocation(entity_id=entry["entityId"])
    return None


# ---------- Flights ----------

def search_flights(
    origin_city: str,
    destination_city: str,
    depart_date: date,
    return_date: Optional[date] = None,
    adults: int = 1,
) -> List[FlightOption]:
    origin = resolve_flight_location(origin_city)
    destination = resolve_flight_location(destination_city)
    if not origin or not destination:
        raise BookingAPIError(f"Could not resolve airport IDs for {origin_city} -> {destination_city}")

    # Confirmed working (2026-07 live test call): currency=USD, market=en-US,
    # countryCode=US as literal values succeed without needing a separate
    # getConfig lookup. Kept as USD (not INR) since that's the confirmed-
    # working value; we still convert to INR ourselves below for display.
    params = {
        "originSkyId": origin.sky_id,
        "destinationSkyId": destination.sky_id,
        "originEntityId": origin.entity_id,
        "destinationEntityId": destination.entity_id,
        "date": depart_date.isoformat(),
        "adults": adults,
        "cabinClass": "economy",
        "sortBy": "best",
        "currency": "USD",
        "market": "en-US",
        "countryCode": "US",
    }
    if return_date:
        params["returnDate"] = return_date.isoformat()

    data = _get("/flights/searchFlights", params, version="v2")  # confirmed: Version 2, not the deprecated v1
    # Confirmed real shape (2026-07 sample from RapidAPI docs):
    # data.itineraries[i] = { id, token, price: {raw, formatted}, legs: [...] }
    # legs[i] = { origin, destination, departure, arrival, durationInMinutes,
    #             stopCount, carriers: {marketing: [{name, alternateId}]},
    #             segments: [{flightNumber, marketingCarrier: {...}}] }
    itineraries = data.get("data", {}).get("itineraries", [])

    options: List[FlightOption] = []
    for offer in itineraries[:10]:
        try:
            # We deliberately don't pass a currency param (see note above),
            # so the API returns its default USD pricing - convert explicitly.
            price_usd = offer.get("price", {}).get("raw", 0)
            from backend.tools.currency import convert
            price_inr = convert(price_usd, "USD", "INR") if price_usd else 0.0

            legs = offer.get("legs", [{}])
            first_leg = legs[0] if legs else {}
            marketing_carriers = first_leg.get("carriers", {}).get("marketing", [{}])
            airline_name = marketing_carriers[0].get("name", "Unknown") if marketing_carriers else "Unknown"
            segments = first_leg.get("segments", [{}])
            flight_no = segments[0].get("flightNumber") if segments else None

            options.append(FlightOption(
                airline=airline_name,
                flight_number=flight_no,
                departure_time=first_leg.get("departure"),
                arrival_time=first_leg.get("arrival"),
                price_inr=price_inr,
                stops=first_leg.get("stopCount", 0),
                raw=offer,
            ))
        except (KeyError, IndexError, TypeError):
            continue  # skip malformed entries rather than crash the whole search
    return options


# ---------- Hotels ----------

def search_hotels(
    destination_city: str,
    checkin: date,
    checkout: date,
    adults: int = 1,
) -> List[HotelOption]:
    hotel_loc = resolve_hotel_location(destination_city)
    if not hotel_loc:
        raise BookingAPIError(f"Could not resolve destination ID for {destination_city}")

    # Confirmed real params (2026-07): entityId, checkin, checkout, adults,
    # rooms, limit, sorting, currency, market, countryCode. Unlike flights,
    # this endpoint's docs don't warn currency/market/countryCode need a
    # separate getConfig lookup, so USD/en-US/US as literal defaults is safe
    # here - but we still convert to INR ourselves for consistency.
    params = {
        "entityId": hotel_loc.entity_id,
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
        "adults": adults,
        "rooms": 1,
        "limit": 30,
        "sorting": "-relevance",
        "currency": "USD",
        "market": "en-US",
        "countryCode": "US",
    }
    data = _get("/hotels/searchHotels", params)
    # Confirmed real shape (2026-07): flat list at data.hotels[i], NOT nested
    # under a 'property' key. Price fields: 'price' (display string like "$10"),
    # 'rawPrice' (numeric, in whatever `currency` param was passed - USD here).
    # 'rating.value' is a STRING (e.g. "3.2"), not a float. 'distance' is a
    # free-text string in MILES (e.g. "3.40 miles from downtown"), not a
    # clean numeric km field - parsed defensively below.
    hotels = data.get("data", {}).get("hotels", [])

    options: List[HotelOption] = []
    for h in hotels[:15]:
        try:
            raw_price_usd = h.get("rawPrice", 0)
            from backend.tools.currency import convert
            price_inr = convert(raw_price_usd, "USD", "INR") if raw_price_usd else 0.0

            rating_block = h.get("rating", {}) or {}
            rating_value = None
            if rating_block.get("value"):
                try:
                    rating_value = float(rating_block["value"])
                except (ValueError, TypeError):
                    rating_value = None

            distance_km = None
            distance_str = h.get("distance", "")
            if distance_str and "mile" in distance_str.lower():
                try:
                    miles = float(distance_str.split()[0])
                    distance_km = round(miles * 1.60934, 2)
                except (ValueError, IndexError):
                    distance_km = None

            options.append(HotelOption(
                name=h.get("name", "Unknown hotel"),
                area=h.get("relevantPoiDistance"),
                price_per_night_inr=price_inr,
                rating=rating_value,
                distance_to_center_km=distance_km,
                raw=h,
            ))
        except (KeyError, TypeError):
            continue
    return options
