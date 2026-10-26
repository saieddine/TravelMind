
from fastapi import FastAPI
from models import TripRequest
from orchestrator import plan_trip
app = FastAPI(
    title="TravelMind API",
    description="An AI-powered travel planning system.",
    version="0.1.0",
)


@app.get("/")
def home():
    return {
        "message": "Welcome to TravelMind!",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "TravelMind API",
    }


@app.post("/api/trips/validate")
def validate_trip(trip: TripRequest):
    return {
        "message": "Trip request received successfully",
        "trip": trip.model_dump(),
        "budget_per_day": round(
            trip.budget / trip.days, 2
        ),
    }
@app.post("/api/trips/plan")
def create_trip_plan(trip: TripRequest):
    return plan_trip(trip)