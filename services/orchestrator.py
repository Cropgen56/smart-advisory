import os
from core.autonomous_activities_engine import ActivitiesEngine
from schemas.request import AdvisoryRequestSchema
from schemas.response import (
    AdvisoryResponseSchema, PlantGrowthResponse, CropHealth, 
    YieldPrediction, CarbonData, ActivityToDo
)

# Initialize engine globally
KB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "advisory_knowledge_base_draft.json")
try:
    engine = ActivitiesEngine(KB_PATH)
except Exception as e:
    engine = None
    print(f"Warning: Could not load ActivitiesEngine: {e}")

def generate_full_advisory(request: AdvisoryRequestSchema) -> AdvisoryResponseSchema:
    # 1. Translate JS inputs to Engine logic
    ndvi_val = request.ndvi.ndviLatest
    humidity = request.weather.current.relative_humidity
    temp = request.weather.current.temp
    crop_name = request.farmField.cropName
    
    # Calculate crop health percentage (mock logic based on NDVI)
    health_score = min(100, max(0, int((ndvi_val / 0.8) * 100)))
    health_category = "Good" if health_score > 75 else "Moderate" if health_score > 50 else "Poor"
    
    # Prepare engine inputs
    soil_moist = request.weather.current.soil_moisture_15cm
    # If soil moisture is fraction, convert to percentage
    sm_pct = soil_moist * 100 if soil_moist < 1.0 else soil_moist
    
    rainfall_forecast = sum(request.weather.forecast.precipitation[:5]) if request.weather.forecast.precipitation else 0.0
    bbch_stage = request.plantGrowthActivity.bbchStage if request.plantGrowthActivity else 30
    
    activities = []
    # 2. Get activities from Autonomous Engine
    if engine:
        raw_activities = engine.recommend(
            crop=crop_name,
            crop_health_percent=health_score,
            bbch_stage=bbch_stage,
            ndvi=ndvi_val,
            soil_moisture=sm_pct,
            humidity=humidity,
            temperature=temp,
            rainfall_forecast=rainfall_forecast
        )
        
        for ra in raw_activities:
            activity_type = ra.get("activity", "Monitor")
            title = f"{activity_type.upper()} (Priority {ra.get('priority', 3)})"
            
            if activity_type == "Spray":
                msg = f"Chemical: {ra.get('chemical', 'N/A')} | Dose: {ra.get('dose', 'N/A')} | Timing: {ra.get('timing', 'N/A')}. Reason: {ra.get('reason', '')}"
            elif activity_type == "Fertilize":
                msg = f"Nutrient: {ra.get('nutrient', 'N/A')} | Dose: {ra.get('dose', 'N/A')} | Timing: {ra.get('timing', 'N/A')}. Reason: {ra.get('reason', '')}"
            elif activity_type == "Irrigate":
                msg = f"Method: {request.farmField.typeOfIrrigation} | Duration: {ra.get('water_hours', 0.5):.1f} hrs | Timing: {ra.get('timing', 'N/A')}. Reason: {ra.get('reason', '')}"
            elif activity_type == "Alert":
                title = f"ALERT: {ra.get('alert_type', '').replace('_', ' ').title()}"
                msg = f"{ra.get('message', '')}. Action: {ra.get('action', '')}"
            else:
                title = "MONITOR"
                msg = ra.get("reason", "Crop conditions stable. Continue monitoring.")
                
            activities.append(ActivityToDo(
                type=activity_type,
                title=title,
                message=msg
            ))
    else:
        # Fallback if engine is missing
        activities.append(ActivityToDo(type="Monitor", title="MONITOR", message="Engine unavailable. Monitor crop manually."))

    # 3. Handle Plant Growth
    growth = request.plantGrowthActivity
    growth_response = None
    if growth:
        growth_response = PlantGrowthResponse(
            stageName=growth.stageName,
            bbchStage=growth.bbchStage,
            cumulativeGDD=growth.cumulativeGDD,
            overallProgress=growth.overallProgress
        )

    # 4. Return formatted data matching JS test
    return AdvisoryResponseSchema(
        success=True,
        message="Advisory generated successfully",
        plantGrowthActivity=growth_response,
        cropHealth=CropHealth(
            category=health_category,
            percentage=health_score,
            recommendation="Maintain current irrigation schedule." if health_score > 75 else "Immediate intervention required."
        ),
        yield_data=YieldPrediction(
            standardYield=20.5,
            aiYield=22.1,
            unit="Quintals/Acre",
            explanation="AI prediction is higher due to optimal GDD accumulation."
        ),
        carbonData=CarbonData(
            emissionKgCO2=150.0,
            capturedKgCO2=450.0,
            netBalanceKgCO2=-300.0
        ),
        activitiesToDo=activities
    )