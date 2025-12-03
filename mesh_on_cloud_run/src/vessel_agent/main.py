import os
import uvicorn
from fastapi import FastAPI, Request

app = FastAPI()

@app.post('/get_vessel_tracks')
async def get_vessel_tracks(request: Request):
    """
    Returns a list of vessel AIS tracks
    """

    # We get the zone from the regulator agent
    data = await request.json()
    zone = data.get('zone', 'unknown')

    # TODO: Use real-world AIS data feed
    vessels = [
        {"id": "vessel-A", "class": "Ferry", "lat": 45.53, "lon": -123.985},
        {"id": "vessel-B", "class": "Recreational", "lat": 45.52, "lon": -123.991},
        {"id": "vessel-C", "class": "Cargo", "lat": 45.56, "lon": -124.01},
        {"id": "vessel-D", "class": "Recreational", "lat": 45.54, "lon": -123.975}
    ]

    return {
        "source": "Mocked AIS Feed",
        "zone": zone,
        "vessel_count": len(vessels),
        "vessels": vessels
    }

# For local testing
if __name__ == "__main__":
    # Use same port as other agent
    port = int(os.environ.get('PORT', 8082))
    uvicorn.run(app, host='0.0.0.0', port=port)