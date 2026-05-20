from core.autonomous_activities_engine import ActivitiesEngine
from core.knowledge import kb_manager
from schemas.request import AdvisoryRequestSchema
from schemas.response import (
    AdvisoryResponseSchema, PlantGrowthResponse, CropHealth,
    YieldPrediction, CarbonData, ActivityToDo
)

# ── Initialise engine once at startup.
# kb_manager is the singleton loaded from CropGen_India_Filled_AAS.xlsx (90 crops).
# It is created when core.knowledge is first imported, so no extra setup needed here.
try:
    engine = ActivitiesEngine(kb_manager)
except Exception as e:
    engine = None
    print(f"Warning: Could not initialise ActivitiesEngine: {e}")

def generate_full_advisory(request: AdvisoryRequestSchema) -> AdvisoryResponseSchema:
    # 1. Extract inputs
    ndvi_val = request.ndvi.ndviLatest
    humidity = request.weather.current.relative_humidity
    temp = request.weather.current.temp
    wind_speed = request.weather.current.wind_speed
    crop_name = request.farmField.cropName
    farming_type = request.farmField.typeOfFarming
    irrigation_type = request.farmField.typeOfIrrigation
    acre = request.farmField.acre
    
    # Get crop agronomic parameters
    crop_kb = kb_manager.get_crop(crop_name)
    
    # Calculate crop health percentage (based on NDVI and crop thresholds)
    ndvi_low = crop_kb.get("ndvi_threshold_for_spray", 0.65)
    ndvi_high = min(ndvi_low + 0.20, 1.0)
    health_score = min(100, max(0, int((ndvi_val / ndvi_high) * 100)))
    health_category = "Good" if health_score > 75 else "Moderate" if health_score > 50 else "Poor"
    
    # Prepare engine inputs
    soil_moist = request.weather.current.soil_moisture_15cm
    sm_pct = soil_moist * 100 if soil_moist <= 1.5 else soil_moist
    
    rainfall_forecast = sum(request.weather.forecast.precipitation[:5]) if request.weather.forecast.precipitation else 0.0
    bbch_stage = request.plantGrowthActivity.bbchStage if request.plantGrowthActivity else 30
    
    # Carbon data (estimated based on farming type, area, and NDVI)
    farming_type_factor = 20.0 if farming_type.lower() == "organic" else 80.0
    carbon_emission = acre * farming_type_factor
    ndvi_capture_factor = 500.0
    carbon_captured = acre * ndvi_val * ndvi_capture_factor
    carbon_net = carbon_emission - carbon_captured
    
    # Prepare forecast data
    forecast_weather = None
    forecast_incomplete = False
    if getattr(request.weather, "forecast", None):
        forecast_weather = request.weather.forecast.model_dump()
        if len(forecast_weather.get("time", [])) < 5:
            forecast_incomplete = True
            
    water_stress_level = getattr(request.water, "stressLevel", "Low") if getattr(request, "water", None) else "Low"
    ndvi_trend = getattr(request.ndvi, "ndviTrend", 0.0) if getattr(request, "ndvi", None) else 0.0
    
    activities = []
    # 2. Get all 7 activities from Autonomous Engine
    if engine:
        raw_activities = engine.recommend(
            crop=crop_name,
            crop_health_percent=health_score,
            bbch_stage=bbch_stage,
            ndvi=ndvi_val,
            soil_moisture=sm_pct,
            humidity=humidity,
            temperature=temp,
            rainfall_forecast=rainfall_forecast,
            wind_speed=wind_speed,
            farming_type=farming_type,
            irrigation_type=irrigation_type,
            acre=acre,
            carbon_emission=carbon_emission,
            carbon_captured=carbon_captured,
            carbon_net=carbon_net,
            forecast_weather=forecast_weather,
            water_stress_level=water_stress_level,
            ndvi_trend=ndvi_trend,
        )
        
        for ra in raw_activities:
            activities.append(ActivityToDo(
                type=ra.get("type", "MONITORING"),
                title=ra.get("title", ""),
                message=ra.get("message", ""),
            ))
            
        if forecast_incomplete:
            activities.append(ActivityToDo(
                type="WEATHER",
                title="System Alert: Incomplete Forecast",
                message="Weather forecast data provided covers less than 5 days. Predictive alerts may be limited."
            ))
    else:
        activities.append(ActivityToDo(type="MONITORING", title="System check", message="Advisory engine unavailable. Monitor crop manually."))

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

    # 4. Yield Prediction
    yield_data_kb = kb_manager.get_yield(crop_name)
    yield_prediction = None
    if yield_data_kb:
        std_yield = yield_data_kb["standard_yield"]
        adjustment = 0.7 + (0.3 * health_score / 100.0)
        ai_yield = round(std_yield * adjustment, 1)
        yield_prediction = YieldPrediction(
            standardYield=std_yield,
            aiYield=ai_yield,
            unit=yield_data_kb["unit"],
            explanation=f"AI prediction scaled based on current crop health ({health_score}%)."
        )

    # 5. Return formatted response
    return AdvisoryResponseSchema(
        success=True,
        message="Advisory generated successfully",
        plantGrowthActivity=growth_response,
        cropHealth=CropHealth(
            category=health_category,
            percentage=health_score,
            recommendation="Maintain current irrigation schedule." if health_score > 75 else "Immediate intervention required."
        ),
        yield_data=yield_prediction,
        carbonData=CarbonData(
            emissionKgCO2=carbon_emission,
            capturedKgCO2=carbon_captured,
            netBalanceKgCO2=carbon_net
        ),
        activitiesToDo=activities
    )