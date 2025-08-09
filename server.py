# server.py
import os
import math
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastmcp import FastMCP
import uvicorn

# Load .env variables
load_dotenv()

# Configuration
SERVER_ID = os.getenv("MCP_SERVER_ID", "near-me-tool")
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
MAX_RESULTS = int(os.getenv("MAX_RESULTS", 6))
DEFAULT_RADIUS_KM = float(os.getenv("DEFAULT_RADIUS_KM", 5.0))

# Validate tool config
EXPECTED_BEARER_TOKEN = os.getenv("BEARER_TOKEN", "abc123token")
OWNER_PHONE_NUMBER = os.getenv("OWNER_PHONE_NUMBER", "919876543210")  # {country_code}{number}

# Initialize FastMCP
mcp = FastMCP(name=SERVER_ID)
app = FastAPI()

# ---------------------------
# Utility functions
# ---------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate the distance in km between two lat/lon points."""
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def overpass_query(lat, lon, radius_km, amenity):
    """Query Overpass API for a specific amenity near given coordinates."""
    radius_m = int(radius_km * 1000)
    query = f"""
[out:json][timeout:25];
(
  node["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
  way["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
  relation["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
);
out center;
"""
    res = requests.post(OVERPASS_URL, data=query, timeout=30)
    res.raise_for_status()

    results = []
    for el in res.json().get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("operator") or "Unknown"
        phone = tags.get("phone") or tags.get("contact:phone") or tags.get("telephone")
        addr_parts = [tags.get(k) for k in [
            "addr:street", "addr:housenumber", "addr:city",
            "addr:postcode", "addr:state", "addr:country"
        ] if tags.get(k)]
        address = ", ".join(addr_parts) or tags.get("addr:full", "Not available")
        lat_e, lon_e = (
            (el.get("lat"), el.get("lon")) if el["type"] == "node"
            else (el.get("center", {}).get("lat"), el.get("center", {}).get("lon"))
        )
        if lat_e is None or lon_e is None:
            continue

        results.append({
            "name": name,
            "address": address,
            "contact": phone or "Not available",
            "lat": lat_e,
            "lon": lon_e,
            "distance_km": haversine_km(lat, lon, lat_e, lon_e)
        })

    return sorted(results, key=lambda r: r["distance_km"])[:MAX_RESULTS]

# ---------------------------
# MCP Tools
# ---------------------------
@mcp.tool()
def find_nearest_hospital(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    """Find the nearest hospitals within the given radius in km."""
    return overpass_query(latitude, longitude, radius_km, "hospital")

@mcp.tool()
def find_nearest_police(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    """Find the nearest police stations within the given radius in km."""
    return overpass_query(latitude, longitude, radius_km, "police")

@mcp.tool()
def find_nearest_fire_station(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    """Find the nearest fire stations within the given radius in km."""
    return overpass_query(latitude, longitude, radius_km, "fire_station")

@mcp.tool()
def find_nearest_public_office(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    """Find the nearest public offices (town halls) within the given radius in km."""
    return overpass_query(latitude, longitude, radius_km, "townhall")

@mcp.tool()
def validate(bearer_token: str) -> str:
    """
    Validate the given bearer token and return the owner's phone number.
    Required for authentication with Puch AI.
    """
    if bearer_token != EXPECTED_BEARER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return OWNER_PHONE_NUMBER

# ---------------------------
# HTTP API Endpoints
# ---------------------------
@app.get("/tools")
def list_tools():
    return {"tools": mcp.list_tools()}

@app.get("/call/{tool_name}")
def call_tool(tool_name: str, latitude: float = None, longitude: float = None,
              radius_km: float = DEFAULT_RADIUS_KM, bearer_token: str = None):
    tools = {
        "find_nearest_hospital": lambda: find_nearest_hospital(latitude, longitude, radius_km),
        "find_nearest_police": lambda: find_nearest_police(latitude, longitude, radius_km),
        "find_nearest_fire_station": lambda: find_nearest_fire_station(latitude, longitude, radius_km),
        "find_nearest_public_office": lambda: find_nearest_public_office(latitude, longitude, radius_km),
        "validate": lambda: validate(bearer_token)
    }
    if tool_name not in tools:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tools[tool_name]()
@app.get("/debug")
def debug():
    return {
        "tools": mcp.list_tools(),
        "routes": [route.path for route in app.routes]
    }

@app.get("/")
def root():
    return {"message": "Near-Me MCP Server is running"}

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 3000))
    print(f"🚀 Starting Near-Me MCP Server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)

