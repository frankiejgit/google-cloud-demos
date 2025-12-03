import os
import time
import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI()

DATA_SOURCE_VERSION = os.environ.get('DATA_SOURCE_VERSION', 'v1')

# Structure of incoming request
class SightingRequest(BaseModel):
    zone: str

@app.post('/get_sightings')
async def get_sightings(request: SightingRequest):
    """
    Returns a list of whale sightings based on service version.
    """

    # Simulate time
    start_time = time.time()

    # Get a 'zone' from the regulator agent
    #data = await request.json()
    zone = request.zone

    print(f"BIOLOGIST AGENT: Received request for zone '{zone}'. Serving with '{DATA_SOURCE_VERSION}'.")

    # If data comes from human sightings, add delay
    if DATA_SOURCE_VERSION == 'v1':
        time.sleep(1)

        # Simulating reported-sightings, data is meant to be sparse
        sightings = [
            {"id": "human-1", "type": "SRKW", "lat": 45.52, "lon": -123.99},
            {"id": "human-2", "type": "SRKW", "lat": 45.55, "lon": -123.98}
        ]

        source = "v1 (Human Sightings)"

    # if v2, we are simulating new acoustic sensors
    else:
        sightings = [
            {"id": "sensor-1", "type": "SRKW", "lat": 45.53, "lon": -123.98},
            {"id": "sensor-2", "type": "SRKW", "lat": 45.54, "lon": -123.97},
            {"id": "sensor-3", "type": "SRKW", "lat": 45.55, "lon": -124.00}
        ]

        source = "v2 (Acoustic Sensor Feed)"

    # Track how long data retrieval took
    duration = time.time() - start_time

    return {
        "source": source,
        "zone": zone,
        "duration_sec": duration,
        "sightings_count": len(sightings),
        "sightings": sightings
    }

# Local testing only - this is meant to run via gunicorn in Cloud Run
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
