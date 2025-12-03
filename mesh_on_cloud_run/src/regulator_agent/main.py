import os
import json
import asyncio
import httpx
import uvicorn 
import pandas as pd
import geopandas as gpd
from geopy.distance import great_circle 
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- Configuration ---
BIOLOGIST_AGENT_URL = os.environ.get("BIOLOGIST_AGENT_URL", "http://127.0.0.1:8081/get_sightings")
VESSEL_AGENT_URL = os.environ.get("VESSEL_AGENT_URL", "http://127.0.0.1:8082/get_vessel_tracks")
LLM_PROXY_URL = os.environ.get("LLM_PROXY_URL", "http://127.0.0.1:8083/generate_summary")
PROJECT_ID=os.environ.get("PROJECT_ID", "multi-agent-run-demo")
REGION = os.environ.get("REGION", "us-central1")

print("--- AGENT STARTUP CONFIGURATION ---")
print(f"BIOLOGIST_AGENT_URL on startup: {BIOLOGIST_AGENT_URL}")
print(f"VESSEL_AGENT_URL on startup: {VESSEL_AGENT_URL}")
print("------------------------------------")

# App info
app = FastAPI(title="ODFW Orca Guardian")
http_client = httpx.AsyncClient(timeout=120.0)

# --- Main Agentic Logic ---
async def get_data_from_agent(service_url: str, zone: str) -> dict:
    """
    Helper function to call another agent or toolset.
    This is intended to be another Cloud Run service within the same service mesh.
    """
    if not service_url:
        raise HTTPException(status_code=500, detail="Service URL for a dependency is not configured.")
    try:
        response = await http_client.post(service_url, json={"zone": zone})
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=503, detail=f"Downstream service unavailable {e.response.text}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=504, detail="Could not connect to downstream service")
    
def analyze_proximity_risk(whale_data: dict, vessel_data: dict) -> list[dict]:
    """
    Analyzes proximity risk using Pandas and GeoPandas. Initially using DuckDB but issues with CPU architecture.
    """
    print("REGULATOR AGENT: Fusing whale and vessels data...")

    whale_sightings = whale_data.get("sightings", [])
    vessel_tracks = vessel_data.get("vessels", [])

    if not whale_sightings or not vessel_tracks:
        print("REGULATOR AGENT: Pre-condition check failed. Skipping analysis.")
        return []

    try:
        # 1. Convert raw data into Pandas DataFrames
        whales_df = pd.DataFrame(whale_sightings)
        vessels_df = pd.DataFrame(vessel_tracks)

        # 2. Create GeoPandas GeoDataFrames with a geometry column
        whales_gdf = gpd.GeoDataFrame(
            whales_df, geometry=gpd.points_from_xy(whales_df.lon, whales_df.lat)
        )
        vessels_gdf = gpd.GeoDataFrame(
            vessels_df, geometry=gpd.points_from_xy(vessels_df.lon, vessels_df.lat)
        )

        # 3. Perform a cross join to create all possible pairs
        all_pairs = whales_gdf.merge(vessels_gdf, how="cross", suffixes=('_whale', '_vessel'))

        # 4. Calculate the distance for each pair using a reliable apply method
        def calculate_distance(row):
            return great_circle(
                (row['geometry_whale'].y, row['geometry_whale'].x),
                (row['geometry_vessel'].y, row['geometry_vessel'].x)
            ).meters

        all_pairs['distance_meters'] = all_pairs.apply(calculate_distance, axis=1)

        # 5. Filter the results to find only those within the 1852-meter threshold
        risk_events_df = all_pairs[all_pairs['distance_meters'] <= 1852].copy()

        # 6. Select, rename, and format the final columns
        risk_events_df.rename(columns={
            'id_vessel': 'vessel_id',
            'class': 'vessel_class',
            'id_whale': 'whale_sighting_id'
        }, inplace=True)
        
        final_report_df = risk_events_df[[
            'vessel_id', 'vessel_class', 'whale_sighting_id', 'distance_meters'
        ]]

        # 7. Return the result as a standard list of dictionaries
        return final_report_df.round({'distance_meters': 0}).to_dict('records')

    except Exception as e:
        print(f"PANDAS/GEOPANDAS ANALYSIS ERROR: {e}") 
        raise HTTPException(status_code=500, detail=f"Data analysis with Pandas failed: {e}")
    
# --- GenAI Summarization ---
async def get_summary_and_action(risk_events: list[dict], zone:str) -> dict:
    """
    Uses Gemini on Vertex AI to interpret analysis and generate summary.
    """
    if not risk_events:
        return {
            "summary": "No high-risk proximity events were detected.",
            "risk_level": "Low",
            "recommended_action": "No action required. Continue monitoring."
        }
    
    print("REGULATOR AGENT: Delegating to Gemini for generative summary...")

    prompt = f"""
    You are an expert risk assessment analyst for the Oregon Department of Fish and Wildlife (ODFW).
    Your task is to analyze a list of close-proximity events between vessels and endangered Southern Resident Killer Whales (SRKWs) in the '{zone}' zone.

    Here is the structured data of the risk events:
    {risk_events}

    Based on this data, provide a JSON object with three keys:
    1. "summary": A concise, human-readable paragraph describing the findings. Mention the number of incidents and highlight the vessel class most involved (e.g., "Recreational").
    2. "risk_level": Classify the overall risk as "Low", "Moderate", "High", or "Critical".
    3. "recommended_action": Suggest a concrete next step for ODFW. For recreational vessels, suggest educational outreach. For commercial vessels, suggest direct contact.
    """

    try:
        response = await http_client.post(LLM_PROXY_URL, json={"prompt": prompt})
        # Check if the request to the proxy was successful before proceeding
        response.raise_for_status() 
        return (response.json())
    except Exception as e:
        print(f"Error calling AI model: {e}")
        # If LLM fails, still return raw data with an unknown risk level
        return {
            "summary": "AI summary generaton failed. See raw data.",
            "risk_level": "Unknown",
            "recommended_action": f"Investigate AI model error: {e}"
        }

# --- API Endpoint(s) ---
class RiskRequest(BaseModel):
    zone: str

@app.post('/check_risk')
async def check_risk(request: RiskRequest):
    """
    Orchestrates agent crew and uses LLM to assess and summarize risk for SRKWs.
    """

    zone = request.zone
    print(f"\n--- REGULATOR AGENT: New risk assessment for zone: {zone} ---")

    # 1. Delegate data collection to crew
    print("REGULATOR AGENT: Delegating to biologist and vessel agents...")
    whale_task = get_data_from_agent(BIOLOGIST_AGENT_URL, zone)
    vessel_task = get_data_from_agent(VESSEL_AGENT_URL, zone)
    results = await asyncio.gather(whale_task, vessel_task, return_exceptions=True)

    # Error handling if issues with delegating
    if any(isinstance(result, Exception) for result in results):
        for result in results:
            if isinstance(result, Exception):
                raise result
            
    whale_data, vessel_data = results
    print(f"REGULATOR AGENT: Received data from {whale_data['source']} and vessel feed.")

    # 2. Synthesize - analyze data
    risk_events = analyze_proximity_risk(whale_data, vessel_data)
    
    # 3. Summarize using LLM
    ai_summary = await get_summary_and_action(risk_events, zone)
    
    print("REGULATOR AGENT: Assessment complete! Returning final result.")

    return {
        "zone": zone,
        "ai_summary": ai_summary,
        "data": {
            "risk_events_found": len(risk_events),
            "risk_events": risk_events
        },
        "raw_data": {
            "whale_data": whale_data,
            "vessel_data": vessel_data
        }
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)