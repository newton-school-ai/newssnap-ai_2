"""NewsSnap AI - API module."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.admin import router as admin_router
from src.api.auth import router as auth_router
from src.api.sources import router as sources_router
from src.api.users import router as users_router

app = FastAPI(
    title="NewsSnap AI API",
    description="API for the NewsSnap AI application",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sources_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admin_router)


@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok"}
