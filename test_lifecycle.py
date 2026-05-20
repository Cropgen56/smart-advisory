import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ENDPOINT = "/v1/api/advisory/external/generate"

def build_payload(
    bbch=15,
    temp=25.0,
    humidity=60.0,
    wind_speed=10.0,
    soil_moisture=0.5,
    ndvi_latest=0.8,
    precipitation=0.0
):
    return {
        "farmField": {
            "cropName": "Tomato",
            "sowingDate": "2024-01-01",
            "acre": 1.0,
            "typeOfFarming": "Inorganic",
            "typeOfIrrigation": "Drip"
        },
        "language": "hi",
        "platform": "web",
        "plantGrowthActivity": {
            "bbchStage": bbch,
            "stageName": "Simulated Stage",
            "description": "Simulated growth stage",
            "cumulativeGDD": 150.0,
            "overallProgress": bbch / 100.0,
            "stageProgress": 0.5
        },
        "weather": {
            "current": {
                "temp": temp,
                "relative_humidity": humidity,
                "precipitation": precipitation,
                "wind_speed": wind_speed,
                "et0_fao_evapotranspiration": 2.5,
                "soil_moisture_5cm": soil_moisture,
                "soil_moisture_15cm": soil_moisture
            },
            "forecast": {
                "time": [f"Day {i+1}" for i in range(7)],
                "temp_mean": [temp]*7,
                "temp_max": [temp]*7,
                "temp_min": [15.0]*7,
                "precipitation": [precipitation]*7,
                "relative_humidity": [humidity]*7,
                "evapotranspiration": [2.5]*7,
                "wind_speed": [wind_speed]*7
            }
        },
        "ndvi": {
            "ndviLatest": ndvi_latest,
            "ndviMean": 0.75,
            "ndviTrend": 0.0,
            "values": [0.7, 0.75, ndvi_latest]
        },
        "water": {
            "waterLatest": 0.5,
            "waterMean": 0.5,
            "stressLevel": "Low",
            "confidence": 0.95
        }
    }

def print_advisory(title, response_data):
    print(f"\\n{'='*60}")
    print(f" STAGE: {title}")
    print(f"{'='*60}")
    
    if not response_data.get("success"):
        print(f"❌ API Failed: {response_data.get('message')}")
        return
        
    print("\\nActivities Generated:")
    for i, act in enumerate(response_data.get("activitiesToDo", [])):
        print(f"  {i+1}. [{act['type']}] {act['title']}")
        print(f"     => {act['message']}")
    print()

def run_lifecycle_test():
    print("🍅 STARTING TOMATO LIFECYCLE SIMULATION 🍅")
    
    # Stage 1: Early Growth (Needs Fertigation)
    # NDVI is very low (0.35) which should trigger a fertigation warning.
    payload1 = build_payload(bbch=15, ndvi_latest=0.35)
    resp1 = client.post(ENDPOINT, json=payload1)
    print_advisory("1. EARLY GROWTH (Low NDVI -> Expecting Fertigation)", resp1.json())
    
    # Stage 2: Vegetative (High Disease Risk)
    # High humidity (92%) and perfect temp (28°C) for fungal growth. 
    # Should trigger high crop risk and an active spray recommendation.
    payload2 = build_payload(bbch=35, ndvi_latest=0.75, temp=28.0, humidity=92.0)
    resp2 = client.post(ENDPOINT, json=payload2)
    print_advisory("2. VEGETATIVE (High Humidity -> Expecting Spray Alert)", resp2.json())
    
    # Stage 3: Flowering (Water Stress)
    # Soil moisture drops to critically low (0.2) during a sensitive stage.
    # Should trigger an irrigation alert.
    payload3 = build_payload(bbch=60, ndvi_latest=0.8, soil_moisture=0.20)
    resp3 = client.post(ENDPOINT, json=payload3)
    print_advisory("3. FLOWERING (Low Moisture -> Expecting Irrigation)", resp3.json())
    
    # Stage 4: Fruiting (Harvest Safety Cut-off)
    # BBCH 85 (Ripening). Even with low NDVI (0.4) and high humidity (90%),
    # the engine should explicitly BLOCK both fertigation and spraying.
    payload4 = build_payload(bbch=85, ndvi_latest=0.40, humidity=90.0, temp=28.0, wind_speed=10.0)
    resp4 = client.post(ENDPOINT, json=payload4)
    print_advisory("4. HARVEST/RIPENING (Expecting Safety Blocks for Spray & Fertigation)", resp4.json())

if __name__ == "__main__":
    run_lifecycle_test()
