from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the router
from routes import router

# Initialize the FastAPI application
app = FastAPI(
    title="CropGen Advisory Engine",
    description="Backend API for generating autonomous crop advisories.",
    version="1.0.0"
)

# Configure CORS 

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace "*" with your specific frontend domains
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Attach our endpoint routes to the main application
app.include_router(router)


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "CropGen Advisory Engine",
        "documentation": "/docs" 
    }