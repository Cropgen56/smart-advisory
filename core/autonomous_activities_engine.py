"""
AUTONOMOUS ACTIVITIES ENGINE
============================
Rule-based advisory engine. Consumes per-crop data from KnowledgeBaseManager
(which reads CropGen_India_Filled_AAS.xlsx) instead of the legacy 5-crop JSON.

Returns ALL 7 activity categories for every advisory call:
  SPRAY → FERTIGATION → IRRIGATION → WEATHER →
  CROP_RISK → MONITORING → CARBON_TRACKING
"""

from typing import List, Dict, Optional
from core.knowledge import KnowledgeBaseManager


class ActivitiesEngine:
    """
    Rule-based advisory engine.

    Args:
        kb: A fully initialised KnowledgeBaseManager instance. The engine
            delegates ALL crop-data lookups to it — no data is hardcoded here.
    """

    def __init__(self, kb: KnowledgeBaseManager):
        self.kb = kb

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    def recommend(
        self,
        crop: str,
        crop_health_percent: float,
        bbch_stage: int,
        ndvi: float,
        soil_moisture: float,
        humidity: float,
        temperature: float,
        rainfall_forecast: float,
        wind_speed: float = 0.0,
        farming_type: str = "Inorganic",
        irrigation_type: str = "Drip",
        acre: float = 1.0,
        carbon_emission: float = 0.0,
        carbon_captured: float = 0.0,
        carbon_net: float = 0.0,
        gdd_accumulated: Optional[float] = None,
        region: str = "default",
        forecast_weather: Optional[Dict[str, List[float]]] = None,
        water_stress_level: str = "Low",
        ndvi_trend: float = 0.0,
    ) -> List[Dict]:
        """
        Generate ALL 7 activity categories matching the frontend layout.

        Always returns exactly 7 items in this order:
          SPRAY → FERTIGATION → IRRIGATION → WEATHER →
          CROP_RISK → MONITORING → CARBON_TRACKING

        If the crop is not in the knowledge base (even after alias resolution),
        safe informational defaults are returned for all 7 categories.
        """
        # ── Resolve crop name (handles aliases: Paddy→Rice, Chili→Chilli, etc.)
        if not self.kb.is_known_crop(crop):
            return self._unknown_crop_defaults(crop)

        # Canonical display name (proper-cased Excel column name)
        display_name = self.kb.get_display_name(crop)

        # Flat dict of all agronomic parameters for this crop
        crop_kb = self.kb.get_crop(crop)

        is_organic = farming_type.lower() == "organic"

        activities = [
            self._decide_spray(
                display_name, crop_kb, crop_health_percent, ndvi,
                humidity, temperature, bbch_stage, rainfall_forecast,
                wind_speed, is_organic,
            ),
            self._decide_fertigation(
                display_name, crop_kb, crop_health_percent, ndvi,
                bbch_stage, soil_moisture, is_organic,
            ),
            self._decide_irrigation(
                display_name, crop_kb, soil_moisture,
                rainfall_forecast, irrigation_type, acre, water_stress_level,
            ),
            self._decide_weather(
                temperature, humidity, rainfall_forecast, wind_speed, forecast_weather,
            ),
            self._decide_crop_risk(
                display_name, crop_kb, crop_health_percent, ndvi,
                humidity, temperature, is_organic,
            ),
            self._decide_monitoring(display_name, crop_kb, crop_health_percent, ndvi, ndvi_trend),
            self._decide_carbon_tracking(carbon_emission, carbon_captured, carbon_net),
        ]

        return activities

    # ------------------------------------------------------------------
    # 1. SPRAY
    # ------------------------------------------------------------------
    def _decide_spray(
        self, crop: str, crop_kb: Dict, health_pct: float, ndvi: float,
        humidity: float, temperature: float, bbch_stage: int,
        rainfall_forecast: float, wind_speed: float, is_organic: bool,
    ) -> Dict:
        
        # ── Harvest Safety
        if bbch_stage >= 85:
            return {
                "type": "SPRAY", "title": "Harvest Safety — Stop Sprays",
                "message": "Crop is approaching harvest. Stop all chemical sprays to prevent residue on the final product. Monitor manually.",
            }

        ndvi_threshold  = crop_kb.get("ndvi_threshold_for_spray", 0.65)
        crit_humidity   = crop_kb.get("critical_humidity", 75.0)
        fungal_temp_min = crop_kb.get("fungal_temp_min", 20.0)
        fungal_temp_max = crop_kb.get("fungal_temp_max", 28.0)

        # ── Block: high wind
        if wind_speed > 40:
            return {
                "type": "SPRAY", "title": "No spray today",
                "message": (
                    f"Do not spray today. Wind speed {wind_speed:.0f} km/h is too high. "
                    f"Wait for calm conditions (below 40 km/h)."
                ),
            }

        # ── Block: rain expected
        if rainfall_forecast > 20:
            return {
                "type": "SPRAY", "title": "No spray today",
                "message": (
                    f"Do not spray today. Rain expected ({rainfall_forecast:.0f} mm). "
                    f"Chemicals will wash off — skip spray today."
                ),
            }

        # ── Organic farms
        if is_organic:
            if health_pct < 80 or ndvi < ndvi_threshold:
                return {
                    "type": "SPRAY", "title": "Organic pest management",
                    "message": (
                        f"Organic farm — no chemical spray. "
                        f"Use neem oil or approved biopesticide per local organic practice. "
                        f"Health {health_pct:.0f}%, NDVI {ndvi:.3f}."
                    ),
                }
            return {
                "type": "SPRAY", "title": "No spray today",
                "message": (
                    "Organic farm — no chemical spray needed today. "
                    "Continue monitoring using neem oil or biopesticides as preventive practice."
                ),
            }

        # ── RULE 1: Fungal risk (uses per-crop humidity & temp thresholds from Excel)
        fungal_risk = (
            humidity >= crit_humidity
            and fungal_temp_min <= temperature <= fungal_temp_max
            and ndvi < ndvi_threshold
        )
        if fungal_risk:
            fungicide = crop_kb.get("primary_fungicide", "Mancozeb 75% WP")
            dose_str  = self._format_dose(crop_kb.get("fungicide_dosage_ml_per_l", 2.0))
            return {
                "type": "SPRAY", "title": "Fungal risk — spray recommended",
                "message": (
                    f"Apply {fungicide} at {dose_str}. "
                    f"Timing: Morning (6–10 AM). "
                    f"Reason: Fungal risk — humidity {humidity:.0f}% (threshold {crit_humidity:.0f}%), "
                    f"temp {temperature:.0f}°C, NDVI {ndvi:.3f} below threshold {ndvi_threshold:.2f}."
                ),
                "chemical": fungicide,
                "dose": dose_str,
                "timing": "early_morning",
            }

        # ── RULE 2: Pest pressure
        if health_pct < 80 and ndvi < (ndvi_threshold - 0.05):
            insecticide = crop_kb.get("primary_insecticide", "Chlorpyrifos 20%EC")
            dose_str    = self._format_dose(crop_kb.get("insecticide_dosage_ml_per_l", 2.0))
            return {
                "type": "SPRAY", "title": "Pest infestation — spray recommended",
                "message": (
                    f"Apply {insecticide} at {dose_str}. "
                    f"Timing: Evening (4–6 PM). "
                    f"Reason: Pest pressure — health at {health_pct:.0f}%, NDVI dropped to {ndvi:.3f}."
                ),
                "chemical": insecticide,
                "dose": dose_str,
                "timing": "late_evening",
            }

        # ── No spray needed
        if wind_speed > 20:
            reason = "Moderate wind — spray conditions not ideal. Monitor closely."
        else:
            reason = "Disease pressure low. No chemical spray needed. Continue regular monitoring."

        return {
            "type": "SPRAY", "title": "No spray today",
            "message": reason,
        }

    # ------------------------------------------------------------------
    # 2. FERTIGATION
    # ------------------------------------------------------------------
    def _decide_fertigation(
        self, crop: str, crop_kb: Dict, health_pct: float, ndvi: float,
        bbch_stage: int, soil_moisture: float, is_organic: bool,
    ) -> Dict:
        
        # ── Agronomic Safety: No fertigation during Ripening/Harvesting (BBCH 80+)
        if bbch_stage >= 80:
            return {
                "type": "FERTIGATION", "title": "No fertigation needed (Ripening Stage)",
                "message": "Crop is in the ripening/harvest phase. Withholding fertilizer to ensure natural maturity and avoid late-stage residue.",
            }

        ndvi_threshold = crop_kb.get("ndvi_threshold_for_fertilize", 0.60)
        needs_fert = ndvi < ndvi_threshold or health_pct < 85

        if is_organic:
            if needs_fert:
                return {
                    "type": "FERTIGATION", "title": "Organic fertilizer",
                    "message": (
                        f"Apply organic compost or vermicompost. "
                        f"Reason: NDVI {ndvi:.3f} (target ≥ {ndvi_threshold:.2f}), health {health_pct:.0f}%. "
                        f"Method: Broadcast or drip-compatible organic liquid. "
                        f"Timing: Morning (6–10 AM)."
                    ),
                }
            return {
                "type": "FERTIGATION", "title": "Organic fertilizer",
                "message": "No organic fertigation needed today. Nutrients balanced.",
            }

        if needs_fert:
            nutrient  = self._get_fertilizer_for_crop(crop, bbch_stage, crop_kb)
            dose_kg   = self._get_fertilizer_dose(nutrient, crop_kb)
            timing    = "tomorrow" if soil_moisture > 30 else "today_evening"
            method    = (
                "Dissolve in water, apply through drip system. "
                "Run drip 30–45 min after injection."
            )
            return {
                "type": "FERTIGATION", "title": "Inorganic (chemical) fertilizer",
                "message": (
                    f"Chemical: {nutrient} — {dose_kg} kg/acre. "
                    f"Morning (6–10 AM), dissolve product, then fertigation or broadcast with irrigation.\n"
                    f"Fertilizer: {nutrient}  |  Qty: {dose_kg} kg/acre\n"
                    f"Method: {method}\n"
                    f"Timing: Morning (6–10 AM), dissolve product, then fertigation or broadcast with irrigation."
                ),
                "nutrient": nutrient,
                "dose": f"{dose_kg} kg/acre",
                "timing": timing,
            }

        return {
            "type": "FERTIGATION", "title": "No fertigation needed",
            "message": (
                f"Nutrient levels adequate. NDVI {ndvi:.3f} ≥ threshold {ndvi_threshold:.2f}. "
                f"No fertigation required today."
            ),
        }

    # ------------------------------------------------------------------
    # 3. IRRIGATION
    # ------------------------------------------------------------------
    def _decide_irrigation(
        self, crop: str, crop_kb: Dict, soil_moisture: float,
        rainfall_forecast: float, irrigation_type: str, acre: float,
        water_stress_level: str,
    ) -> Dict:

        sm_critical = crop_kb.get("soil_moisture_critical", 35.0)
        ideal_range = crop_kb.get("ideal_range", "50-70%")
        method = irrigation_type or "Drip"
        
        # Severe water stress alert overrides everything
        if water_stress_level.lower() in ["high", "severe"]:
            return {
                "type": "IRRIGATION", "title": "Urgent: Water Stress Detected",
                "message": (
                    f"Sensor indicates {water_stress_level.lower()} water stress. "
                    f"Immediate irrigation required to prevent permanent wilting."
                ),
                "method": method,
                "timing": "immediately",
            }

        if rainfall_forecast > 20:
            return {
                "type": "IRRIGATION", "title": "Irrigation Schedule",
                "message": (
                    f"Skip irrigation. Rain expected ({rainfall_forecast:.0f} mm in next 5 days). "
                    f"Soil moisture at {soil_moisture:.0f}%."
                ),
            }

        if soil_moisture < sm_critical:
            water_hours = self._calculate_water_hours(soil_moisture, crop_kb)
            water_mm    = round(water_hours * 13)  # rough estimate
            method      = irrigation_type or "Drip"
            return {
                "type": "IRRIGATION", "title": "Irrigation Schedule",
                "message": (
                    f"Give {method.lower()} irrigation for about {water_hours:.1f} hours today. "
                    f"(~{water_mm} mm)\n"
                    f"Qty: {water_mm} mm  |  Method: {method}/Sprinkler ~{int(water_hours * 60)} min  |  "
                    f"Time: Morning (6–10 AM)"
                ),
                "method": method,
                "water_hours": water_hours,
                "timing": "today_morning",
            }

        return {
            "type": "IRRIGATION", "title": "Irrigation Schedule",
            "message": (
                f"Soil moisture adequate at {soil_moisture:.0f}% "
                f"(ideal range {ideal_range}). "
                f"No immediate irrigation needed. Next check in 2–3 days."
            ),
        }

    # ------------------------------------------------------------------
    # 4. WEATHER
    # ------------------------------------------------------------------
    def _decide_weather(
        self, temperature: float, humidity: float,
        rainfall_forecast: float, wind_speed: float,
        forecast: Optional[Dict[str, List[float]]] = None,
    ) -> Dict:

        alerts = []
        # Check current conditions
        if temperature > 35:
            alerts.append(f"Max temp {temperature:.1f}°C today. Monitor for heat stress.")
        if temperature < 5:
            alerts.append(f"Low temp {temperature:.1f}°C. Watch for frost risk on sensitive crops.")
        if rainfall_forecast > 30:
            alerts.append(f"Heavy rain ({rainfall_forecast:.0f} mm) expected. Delay spray until 2 days after rain.")
        if wind_speed > 30:
            alerts.append(f"High wind ({wind_speed:.0f} km/h). Do not spray.")
        if humidity > 85:
            alerts.append(f"Very high humidity ({humidity:.0f}%). Increased fungal disease risk.")

        # Check forecast arrays if provided
        if forecast:
            # Operational alerts (3 days lookahead)
            wind_forecast = forecast.get("wind_speed", [])
            if any(w > 40 for w in wind_forecast[:3]):
                day_idx = next(i for i, w in enumerate(wind_forecast[:3]) if w > 40)
                alerts.append(f"High wind (>40 km/h) forecasted in {day_idx + 1} days. Delay sprays.")
            
            # Trend alerts (5 days lookahead)
            temp_max = forecast.get("temp_max", [])
            if any(t > 38 for t in temp_max[:5]):
                day_idx = next(i for i, t in enumerate(temp_max[:5]) if t > 38)
                alerts.append(f"Heatwave risk (>38°C) expected in {day_idx + 1} days. Ensure deep irrigation beforehand.")
                
            temp_min = forecast.get("temp_min", [])
            if any(t < 4 for t in temp_min[:5]):
                day_idx = next(i for i, t in enumerate(temp_min[:5]) if t < 4)
                alerts.append(f"Frost risk (<4°C) expected in {day_idx + 1} days. Protect sensitive crops.")

        if alerts:
            title = "High temperature alert" if temperature > 35 else "Weather alert"
            return {
                "type": "WEATHER", "title": title,
                "message": " ".join(alerts),
            }

        return {
            "type": "WEATHER", "title": "Weather update",
            "message": (
                f"Temp {temperature:.1f}°C, humidity {humidity:.0f}%, "
                f"wind {wind_speed:.0f} km/h. Conditions normal. No weather alerts."
            ),
        }

    # ------------------------------------------------------------------
    # 5. CROP RISK
    # ------------------------------------------------------------------
    def _decide_crop_risk(
        self, crop: str, crop_kb: Dict, health_pct: float, ndvi: float,
        humidity: float, temperature: float, is_organic: bool,
    ) -> Dict:

        ndvi_threshold  = crop_kb.get("ndvi_threshold_for_spray", 0.65)
        crit_humidity   = crop_kb.get("critical_humidity", 75.0)
        fungal_temp_min = crop_kb.get("fungal_temp_min", 20.0)
        fungal_temp_max = crop_kb.get("fungal_temp_max", 28.0)
        diseases        = crop_kb.get("primary_fungal_disease", "Fungal diseases")
        pests           = crop_kb.get("primary_pest", "Common pests")

        # Calculate risk score using per-crop thresholds
        risk_score = 0
        if humidity >= crit_humidity:
            risk_score += 2
        if fungal_temp_min <= temperature <= fungal_temp_max:
            risk_score += 1
        if ndvi < ndvi_threshold:
            risk_score += 2
        if health_pct < 70:
            risk_score += 2

        if risk_score >= 5:
            risk_level = "High"
            if is_organic:
                msg = (
                    f"Organic farm. High risk detected. "
                    f"Use approved biocontrol or neem-based products only — no synthetic sprays.\n"
                    f"Watch for: {diseases}. Common pests: {pests}."
                )
            else:
                msg = (
                    f"High disease/pest risk. Common diseases: {diseases}. "
                    f"Common pests: {pests}. Scout field and spray if threshold exceeded."
                )
        elif risk_score >= 3:
            risk_level = "Medium"
            msg = (
                f"Moderate risk. Watch for: {diseases}. "
                f"Increase monitoring frequency. Prepare sprays if symptoms appear."
            )
        else:
            risk_level = "Low"
            msg = "Disease pressure low. No chemical spray needed. Continue regular monitoring."

        return {
            "type": "CROP_RISK",
            "title": f"{risk_level} disease risk",
            "message": msg,
            "risk_level": risk_level,
        }

    # ------------------------------------------------------------------
    # 6. MONITORING
    # ------------------------------------------------------------------
    def _decide_monitoring(
        self, crop: str, crop_kb: Dict, health_pct: float, ndvi: float, ndvi_trend: float,
    ) -> Dict:
        tips = []
        
        if ndvi_trend <= -0.05:
            tips.append(
                f"URGENT: NDVI has dropped sharply (trend {ndvi_trend:.3f}). "
                "Immediate field scouting required to identify cause (pest/disease/water stress)."
            )
        else:
            tips.append("Check lower leaves, stem base, and new growth for any stress or pest signs.")

        if health_pct < 70:
            tips.append(f"Health is low ({health_pct:.0f}%). Look for yellowing, wilting, or lesions.")
        if ndvi < 0.5:
            tips.append(f"NDVI very low ({ndvi:.3f}). Inspect canopy density and leaf color.")

        pests = crop_kb.get("primary_pest", "")
        if pests:
            tips.append(f"Watch for: {pests}.")

        diseases = crop_kb.get("primary_fungal_disease", "")
        if diseases:
            tips.append(f"Monitor for: {diseases}.")

        return {
            "type": "MONITORING",
            "title": "Crop monitoring",
            "message": " ".join(tips),
        }

    # ------------------------------------------------------------------
    # 7. CARBON TRACKING
    # ------------------------------------------------------------------
    def _decide_carbon_tracking(
        self, emission: float, captured: float, net: float,
    ) -> Dict:
        if net < 0:
            balance_msg = f"Net CO2 balance positive: {abs(net):.1f} kg CO2 captured."
        else:
            balance_msg = f"Net CO2 balance: {net:.1f} kg CO2 emitted."

        return {
            "type": "CARBON_TRACKING",
            "title": "Carbon tracking update",
            "message": (
                f"Emissions: {emission:.1f} kg CO2, "
                f"Captured: {captured:.1f} kg CO2, "
                f"Net: {net:.1f} kg CO2. {balance_msg}"
            ),
        }

    # ------------------------------------------------------------------
    # UNKNOWN CROP FALLBACK
    # ------------------------------------------------------------------
    def _unknown_crop_defaults(self, crop: str) -> List[Dict]:
        """
        Returned when a crop is not found in the knowledge base even after
        alias resolution. Gives safe, generic guidance instead of crashing.
        """
        note = f"Crop '{crop}' is not in the knowledge base."
        return [
            {
                "type": "SPRAY", "title": "No spray today",
                "message": f"{note} Monitor spray conditions manually.",
            },
            {
                "type": "FERTIGATION", "title": "No fertigation needed",
                "message": f"{note} No fertilizer recommendation available. Consult an agronomist.",
            },
            {
                "type": "IRRIGATION", "title": "Irrigation Schedule",
                "message": f"{note} Check soil moisture manually and irrigate if below 35%.",
            },
            {
                "type": "WEATHER", "title": "Weather update",
                "message": "Check local weather forecast for alerts.",
            },
            {
                "type": "CROP_RISK", "title": "Unknown risk",
                "message": f"{note} Monitor for pests and disease manually.",
            },
            {
                "type": "MONITORING", "title": "Crop monitoring",
                "message": "Inspect crop visually. Report any stress signs.",
            },
            {
                "type": "CARBON_TRACKING", "title": "Carbon tracking update",
                "message": "No carbon tracking data available for this crop.",
            },
        ]

    # ------------------------------------------------------------------
    # HELPER METHODS
    # ------------------------------------------------------------------
    def _format_dose(self, dose_value) -> str:
        """Convert raw dose value (from Excel) to a display string."""
        try:
            return f"{float(dose_value):.1f} ml/L"
        except (ValueError, TypeError):
            return "2.0 ml/L"

    def _get_fertilizer_for_crop(
        self, crop: str, bbch_stage: int, crop_kb: Dict,
    ) -> str:
        """
        Selects the right fertilizer based on BBCH stage and per-crop
        data from the knowledge base.

        Logic:
          - Early stages (bbch < 40):   Default NPK mix from Excel
          - Later stages:               Stage-specific chemical from Excel
                                        (falls back to NPK if not set)
        """
        default_npk  = crop_kb.get("default_npk_mix", "19:19:19")
        npk_label    = f"NPK {default_npk}"
        stage_chem   = crop_kb.get("stage_specific_chemical", "")

        if bbch_stage < 40:
            return npk_label

        # Use stage-specific chemical if available; otherwise stay with NPK
        if stage_chem and stage_chem.strip():
            return stage_chem.strip()

        return npk_label

    def _get_fertilizer_dose(self, nutrient: str, crop_kb: Dict) -> float:
        """
        Returns dose in kg/acre.
        NPK dose comes from the Excel per-crop value.
        Urea and MOP use standard agronomic defaults (Excel doesn't carry them yet).
        """
        # Per-crop NPK dose from Excel
        if "npk" in nutrient.lower() or "19" in nutrient:
            return float(crop_kb.get("default_npk_dose_kg_per_acre", 25.0))

        # Standard agronomic defaults for named fertilizers
        standard_doses = {
            "urea":  50.1,
            "mop":   40.5,
        }
        return standard_doses.get(nutrient.lower(), 25.0)

    def _calculate_water_hours(self, soil_moisture: float, crop_kb: Dict) -> float:
        """
        Estimates irrigation duration in hours.
        Uses the per-crop critical moisture target from the knowledge base
        instead of a hardcoded value.
        """
        sm_critical = float(crop_kb.get("soil_moisture_critical", 35.0))
        # Target: bring soil up to the critical threshold
        deficit = max(0.0, sm_critical - soil_moisture)
        return round((deficit / 10) * 0.5, 1)
