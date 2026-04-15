"""
AUTONOMOUS ACTIVITIES ENGINE
============================
Replaces LLM-powered recommendations with rule-based system.
"""

import json
from typing import List, Dict, Optional
from datetime import datetime
import os

class ActivitiesEngine:
    def __init__(self, knowledge_base_path: str):
        """Load knowledge base from JSON file"""
        if not os.path.exists(knowledge_base_path):
            raise FileNotFoundError(f"Knowledge base not found at: {knowledge_base_path}")
        with open(knowledge_base_path) as f:
            self.kb = json.load(f)
        
        # Build case-insensitive crop name lookup: {"wheat": "Wheat", "tomato": "Tomato", ...}
        self._crop_name_map = {
            name.lower(): name for name in self.kb.get("crops", {}).keys()
        }
    
    def _resolve_crop_name(self, crop: str) -> Optional[str]:
        """Resolve crop name case-insensitively. Returns the KB key or None."""
        # Try exact match first
        if crop in self.kb.get("crops", {}):
            return crop
        # Try case-insensitive match
        return self._crop_name_map.get(crop.lower())
    
    def recommend(self, 
                  crop: str,
                  crop_health_percent: float,
                  bbch_stage: int,
                  ndvi: float,
                  soil_moisture: float,
                  humidity: float,
                  temperature: float,
                  rainfall_forecast: float,
                  gdd_accumulated: Optional[float] = None,
                  region: str = "default") -> List[Dict]:
        """Generate list of activities based on field conditions."""
        
        activities = []
        
        # Resolve crop name (case-insensitive)
        resolved_crop = self._resolve_crop_name(crop)
        if not resolved_crop:
            return [{"activity": "Monitor", "reason": f"Crop {crop} not in knowledge base. Monitor conditions.", "priority": 3}]
        
        crop = resolved_crop
        crop_kb = self.kb["crops"][crop]
        
        # ===== SPRAY DECISION =====
        spray_activity = self._recommend_spray(
            crop, crop_health_percent, ndvi, humidity, temperature, bbch_stage
        )
        if spray_activity:
            activities.append(spray_activity)
        
        # ===== FERTILIZER DECISION =====
        fert_activity = self._recommend_fertilizer(
            crop, crop_health_percent, ndvi, bbch_stage, soil_moisture
        )
        if fert_activity:
            activities.append(fert_activity)
        
        # ===== IRRIGATION DECISION =====
        irr_activity = self._recommend_irrigation(
            crop, crop_health_percent, soil_moisture, rainfall_forecast
        )
        if irr_activity:
            activities.append(irr_activity)
        
        # ===== WEATHER ALERTS =====
        weather_activity = self._check_weather_alerts(
            temperature, humidity, rainfall_forecast
        )
        if weather_activity:
            activities.append(weather_activity)
        
        # If no urgent activities, add Monitor
        if not activities:
            activities.append({
                "activity": "Monitor",
                "reason": "Crop conditions stable. Continue monitoring.",
                "priority": 3
            })
        
        # Sort by priority (1=urgent first)
        activities.sort(key=lambda x: x.get("priority", 3))
        
        return activities
    
    def _recommend_spray(self, crop: str, health_pct: float, ndvi: float, 
                        humidity: float, temperature: float, bbch_stage: int) -> Optional[Dict]:
        crop_kb = self.kb["crops"][crop]
        ndvi_threshold = crop_kb.get("ndvi_threshold_for_spray", 0.70)
        
        # RULE 1: Fungal risk (high humidity + moderate temp + low NDVI)
        fungal_risk = (humidity > 70) and (20 <= temperature <= 28) and (ndvi < ndvi_threshold)
        
        if fungal_risk:
            chemical = self._get_fungicide_for_crop(crop)
            return {
                "activity": "Spray",
                "chemical": chemical,
                "dose": "2.5 ml/L",
                "timing": "early_morning",
                "reason": f"Fungal risk: humidity {humidity:.0f}%, temp {temperature:.0f}°C, NDVI below threshold at {ndvi:.3f}",
                "priority": 1
            }
        
        # RULE 2: Pest pressure (health declining, NDVI drop)
        if health_pct < 80 and ndvi < (ndvi_threshold - 0.05):
            chemical = self._get_insecticide_for_crop(crop)
            return {
                "activity": "Spray",
                "chemical": chemical,
                "dose": "2.0 ml/L",
                "timing": "late_evening",
                "reason": f"Pest infestation: health at {health_pct}%, NDVI dropped to {ndvi:.3f}",
                "priority": 2
            }
        
        return None
    
    def _recommend_fertilizer(self, crop: str, health_pct: float, ndvi: float,
                             bbch_stage: int, soil_moisture: float) -> Optional[Dict]:
        crop_kb = self.kb["crops"][crop]
        ndvi_threshold = crop_kb.get("ndvi_threshold_for_fertilize", 0.65)
        
        # RULE: Apply fertilizer if NDVI below threshold or health declining
        if ndvi < ndvi_threshold or health_pct < 85:
            nutrient = self._get_fertilizer_for_crop(crop, bbch_stage)
            dose = self._get_fertilizer_dose(nutrient)
            
            return {
                "activity": "Fertilize",
                "nutrient": nutrient,
                "dose": f"{dose} kg/acre",
                "method": "drip",
                "timing": "tomorrow" if soil_moisture > 30 else "today_evening",
                "reason": f"Nutrient deficiency risk: NDVI {ndvi:.3f} (target {ndvi_threshold}), health {health_pct}%",
                "priority": 2
            }
        
        return None
    
    def _recommend_irrigation(self, crop: str, health_pct: float, 
                             soil_moisture: float, rainfall_forecast: float) -> Optional[Dict]:
        crop_kb = self.kb["crops"][crop]
        soil_moisture_critical = crop_kb.get("soil_moisture_critical", 35)
        
        # RULE: Irrigate if soil moisture critical and no rain expected
        if soil_moisture < soil_moisture_critical and rainfall_forecast < 10:
            water_hours = self._calculate_water_hours(soil_moisture, crop)
            
            return {
                "activity": "Irrigate",
                "method": "drip",
                "water_hours": water_hours,
                "timing": "today_evening",
                "reason": f"Soil moisture low: {soil_moisture:.0f}% (threshold {soil_moisture_critical}%), no heavy rain forecast",
                "priority": 1
            }
        
        return None
    
    def _check_weather_alerts(self, temperature: float, humidity: float,
                             rainfall_forecast: float) -> Optional[Dict]:
        
        if temperature > 35:
            return {
                "activity": "Alert",
                "alert_type": "extreme_heat",
                "message": f"Temperature {temperature:.0f}°C is very high",
                "action": "Increase irrigation frequency. Avoid spraying.",
                "priority": 1
            }
        
        if temperature < 0:
            return {
                "activity": "Alert",
                "alert_type": "frost_risk",
                "message": f"Frost risk: temperature {temperature:.0f}°C",
                "action": "Protect sensitive crops. Skip spray.",
                "priority": 1
            }
        
        if rainfall_forecast > 30:
            return {
                "activity": "Alert",
                "alert_type": "heavy_rain",
                "message": f"Heavy rain ({rainfall_forecast:.0f}mm) expected",
                "action": "Delay spray until 2 days after rain.",
                "priority": 1
            }
        
        return None
    
    def _get_fungicide_for_crop(self, crop: str) -> str:
        fungicides = {
            "Tomato": "Mancozeb 75% WP",
            "Wheat": "Chlorpyrifos 20%EC",
            "Paddy": "Chlorpyrifos 20%EC",
            "Chili": "Mancozeb 75% WP",
            "Cotton": "Alpha-cypermethrin 10%EC",
        }
        return fungicides.get(crop, "Mancozeb 75% WP")
    
    def _get_insecticide_for_crop(self, crop: str) -> str:
        insecticides = {
            "Tomato": "Chlorpyrifos 20%EC",
            "Wheat": "Chlorpyrifos 20%EC",
            "Paddy": "Chlorpyrifos 20%EC",
            "Chili": "Chlorpyrifos 20%EC",
            "Cotton": "Profenofos 50%EC",
        }
        return insecticides.get(crop, "Chlorpyrifos 20%EC")
    
    def _get_fertilizer_for_crop(self, crop: str, bbch_stage: int) -> str:
        if bbch_stage < 40:
            return "NPK 19:19:19"
        
        if crop in ["Paddy", "Wheat"]:
            return "Urea" if bbch_stage > 60 else "NPK 19:19:19"
        elif crop in ["Chili", "Cotton"]:
            return "MOP" if bbch_stage > 50 else "NPK 19:19:19"
        else:
            return "NPK 19:19:19"
    
    def _get_fertilizer_dose(self, nutrient: str) -> float:
        doses = {
            "NPK 19:19:19": 24.2,
            "Urea": 50.1,
            "MOP": 40.5,
        }
        return doses.get(nutrient, 25)
    
    def _calculate_water_hours(self, soil_moisture: float, crop: str) -> float:
        deficit = max(0, 40 - soil_moisture)
        return (deficit / 10) * 0.5

