"""Vercel entrypoint for the Smart Plant Monitor FastAPI application."""

from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from plant_monitor_app import app

# Allow cross-origin requests so the endpoint can be called from the frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

handler = Mangum(app)
