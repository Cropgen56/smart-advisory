import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ENDPOINT = "/v1/api/advisory/external/generate"

def build_payload(
    crop_name="Tomato",
    temp=25.0,
    wind_speed=10.0,
    soil_moisture=0.5,
    stress_level="Low",
    ndvi_latest=0.8,
    ndvi_trend=0.01,
    forecast_days=7,
    forecast_wind=None,
    forecast_temp=None,
    farming_type="Inorganic"
):
    if forecast_wind is None:
        forecast_wind = [10.0] * forecast_days
    if forecast_temp is None:
        forecast_temp = [25.0] * forecast_days
        
    return {
        "farmField": {
            "cropName": crop_name,
            "sowingDate": "2024-01-01",
            "acre": 2.5,
            "typeOfFarming": farming_type,
            "typeOfIrrigation": "Drip"
        },
        "language": "hi",
        "platform": "web",
        "weather": {
            "current": {
                "temp": temp,
                "relative_humidity": 60.0,
                "precipitation": 0.0,
                "wind_speed": wind_speed,
                "et0_fao_evapotranspiration": 2.5,
                "soil_moisture_5cm": soil_moisture,
                "soil_moisture_15cm": soil_moisture
            },
            "forecast": {
                "time": [f"Day {i+1}" for i in range(forecast_days)],
                "temp_mean": forecast_temp,
                "temp_max": forecast_temp,
                "temp_min": [15.0] * forecast_days,
                "precipitation": [0.0] * forecast_days,
                "relative_humidity": [60.0] * forecast_days,
                "evapotranspiration": [2.5] * forecast_days,
                "wind_speed": forecast_wind
            }
        },
        "ndvi": {
            "ndviLatest": ndvi_latest,
            "ndviMean": 0.75,
            "ndviTrend": ndvi_trend,
            "values": [0.7, 0.75, ndvi_latest]
        },
        "water": {
            "waterLatest": 0.5,
            "waterMean": 0.5,
            "stressLevel": stress_level,
            "confidence": 0.95
        }
    }

def print_advisory(title, response_data):
    print(f"\\n{'='*50}")
    print(f" TEST: {title}")
    print(f"{'='*50}")
    
    if not response_data.get("success"):
        print(f"❌ API Failed: {response_data.get('message')}")
        return
        
    print(f"✅ API Success")
    print(f"Crop Health: {response_data['cropHealth']['percentage']}% ({response_data['cropHealth']['category']})")
    
    if response_data.get("yield"):
        yd = response_data["yield"]
        print(f"Yield: Predicted {yd['aiYield']} {yd['unit']} (Standard: {yd['standardYield']} {yd['unit']})")
        
    print("\\nActivities Generated:")
    for i, act in enumerate(response_data.get("activitiesToDo", [])):
        print(f"  {i+1}. [{act['type']}] {act['title']}")
        print(f"     => {act['message']}")
    print()

def run_tests():
    # 1. Happy Path
    payload1 = build_payload(crop_name="Mango", ndvi_latest=0.85)
    resp1 = client.post(ENDPOINT, json=payload1)
    assert resp1.status_code == 200, f"Expected 200, got {resp1.status_code}"
    print_advisory("Scenario 1: Happy Path (Mango, Healthy)", resp1.json())
    
    # 2. Severe Water Stress (Bug #14 fix)
    payload2 = build_payload(crop_name="Rice", stress_level="Severe")
    resp2 = client.post(ENDPOINT, json=payload2)
    assert resp2.status_code == 200
    print_advisory("Scenario 2: Severe Water Stress (Rice)", resp2.json())
    
    # 3. Forecast Alerts & Rapid Decline (Bug #13 & #15 fix)
    payload3 = build_payload(
        crop_name="Cotton", 
        ndvi_trend=-0.12, 
        forecast_wind=[10, 15, 45, 10, 10, 10, 10], # Wind spike on day 3
        forecast_temp=[25, 26, 25, 39, 40, 30, 25]  # Heatwave on day 4
    )
    resp3 = client.post(ENDPOINT, json=payload3)
    assert resp3.status_code == 200
    print_advisory("Scenario 3: Wind Forecast + Heatwave + NDVI Drop (Cotton)", resp3.json())
    
    # 4. Incomplete Forecast Data (Bug #16 fix)
    payload4 = build_payload(crop_name="Tomato", forecast_days=2)
    resp4 = client.post(ENDPOINT, json=payload4)
    assert resp4.status_code == 200
    print_advisory("Scenario 4: Incomplete Forecast (2 days only)", resp4.json())
    
    print("🎉 All E2E tests passed successfully!")

if __name__ == "__main__":
    run_tests()
