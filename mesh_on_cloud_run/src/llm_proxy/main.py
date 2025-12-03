import os
import uvicorn
import json
import time
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

# Initialize FastAPI app
app = FastAPI()

# Pydantic model for the incoming request body
class PromptRequest(BaseModel):
    prompt: str

# Function to access the Gemini API key from Secret Manager
def get_gemini_api_key():
    """
    Retrieves the Gemini API key from an environment variable.
    In Cloud Run, this environment variable will be populated from Secret Manager.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY secret not configured")
    return api_key

# Configure the Gemini API with the retrieved key
try:
    gemini_api_key = get_gemini_api_key()
    genai.configure(api_key=gemini_api_key)
    llm = genai.GenerativeModel('gemini-2.0-flash')
except HTTPException as e:
    # This will prevent the application from starting if the secret is not available
    print(f"Error: {e.detail}")
    exit(1)

@app.post("/generate_summary")
async def generate_summary(request: PromptRequest):
    """
    Receives a prompt, sends it to the Gemini API, and returns the response.
    """
    try:

        start_time = time.time()
        print("LLM PROXY: Received request. Calling Gemini API...")

        # Generate content based on the prompt
        response = await llm.generate_content_async(request.prompt)

        end_time = time.time()
        duration = end_time - start_time
        print(f"LLM PROXY: Gemini API call successful. Duration: {duration:.2f} seconds.")

        clean_response = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Gemini API service is running."}

# Local testing only - this is meant to run via gunicorn in Cloud Run
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8083))
    uvicorn.run(app, host="0.0.0.0", port=port)