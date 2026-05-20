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
from core.i18n import I18n


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
        language: str = "en",
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
            return self._unknown_crop_defaults(crop, language)

        # Canonical display name (proper-cased Excel column name)
        display_name = self.kb.get_display_name(crop)

        # Flat dict of all agronomic parameters for this crop
        crop_kb = self.kb.get_crop(crop)

        is_organic = farming_type.lower() == "organic"
        t = I18n(language)

        activities = [
            self._decide_spray(
                display_name, crop_kb, crop_health_percent, ndvi,
                humidity, temperature, bbch_stage, rainfall_forecast,
                wind_speed, is_organic, t,
            ),
            self._decide_fertigation(
                display_name, crop_kb, crop_health_percent, ndvi,
                bbch_stage, soil_moisture, is_organic, t,
            ),
            self._decide_irrigation(
                display_name, crop_kb, soil_moisture,
                rainfall_forecast, irrigation_type, acre, water_stress_level, t,
            ),
            self._decide_weather(
                temperature, humidity, rainfall_forecast, wind_speed, forecast_weather, t,
            ),
            self._decide_crop_risk(
                display_name, crop_kb, crop_health_percent, ndvi,
                humidity, temperature, is_organic, t,
            ),
            self._decide_monitoring(display_name, crop_kb, crop_health_percent, ndvi, ndvi_trend, t),
            self._decide_carbon_tracking(carbon_emission, carbon_captured, carbon_net, t),
        ]

        return activities

    # ------------------------------------------------------------------
    # 1. SPRAY
    # ------------------------------------------------------------------
    def _decide_spray(
        self, crop: str, crop_kb: Dict, health_pct: float, ndvi: float,
        humidity: float, temperature: float, bbch_stage: int,
        rainfall_forecast: float, wind_speed: float, is_organic: bool,
        t: I18n,
    ) -> Dict:

        # ── Harvest Safety
        if bbch_stage >= 85:
            return {
                "type": "SPRAY",
                "title": t.get("spray.harvest_safety_title"),
                "message": t.get("spray.harvest_safety_message"),
            }

        ndvi_threshold  = crop_kb.get("ndvi_threshold_for_spray", 0.65)
        crit_humidity   = crop_kb.get("critical_humidity", 75.0)
        fungal_temp_min = crop_kb.get("fungal_temp_min", 20.0)
        fungal_temp_max = crop_kb.get("fungal_temp_max", 28.0)

        # ── Block: high wind
        if wind_speed > 40:
            return {
                "type": "SPRAY",
                "title": t.get("spray.high_wind_title"),
                "message": t.get("spray.high_wind_message", wind_speed=f"{wind_speed:.0f}"),
            }

        # ── Block: rain expected
        if rainfall_forecast > 20:
            return {
                "type": "SPRAY",
                "title": t.get("spray.rain_block_title"),
                "message": t.get("spray.rain_block_message", rainfall=f"{rainfall_forecast:.0f}"),
            }

        # ── Organic farms
        if is_organic:
            if health_pct < 80 or ndvi < ndvi_threshold:
                return {
                    "type": "SPRAY",
                    "title": t.get("spray.organic_risk_title"),
                    "message": t.get("spray.organic_risk_message",
                                     health=f"{health_pct:.0f}", ndvi=f"{ndvi:.3f}"),
                }
            return {
                "type": "SPRAY",
                "title": t.get("spray.organic_ok_title"),
                "message": t.get("spray.organic_ok_message"),
            }

        # ── RULE 1: Fungal risk
        fungal_risk = (
            humidity >= crit_humidity
            and fungal_temp_min <= temperature <= fungal_temp_max
            and ndvi < ndvi_threshold
        )
        if fungal_risk:
            fungicide = crop_kb.get("primary_fungicide", "Mancozeb 75% WP")
            dose_str  = self._format_dose(crop_kb.get("fungicide_dosage_ml_per_l", 2.0))
            return {
                "type": "SPRAY",
                "title": t.get("spray.fungal_title"),
                "message": t.get("spray.fungal_message",
                                  chemical=fungicide, dose=dose_str,
                                  humidity=f"{humidity:.0f}", crit_humidity=f"{crit_humidity:.0f}",
                                  temp=f"{temperature:.0f}", ndvi=f"{ndvi:.3f}",
                                  ndvi_threshold=f"{ndvi_threshold:.2f}"),
                "chemical": fungicide,
                "dose": dose_str,
                "timing": "early_morning",
            }

        # ── RULE 2: Pest pressure
        if health_pct < 80 and ndvi < (ndvi_threshold - 0.05):
            insecticide = crop_kb.get("primary_insecticide", "Chlorpyrifos 20%EC")
            dose_str    = self._format_dose(crop_kb.get("insecticide_dosage_ml_per_l", 2.0))
            return {
                "type": "SPRAY",
                "title": t.get("spray.pest_title"),
                "message": t.get("spray.pest_message",
                                  chemical=insecticide, dose=dose_str,
                                  health=f"{health_pct:.0f}", ndvi=f"{ndvi:.3f}"),
                "chemical": insecticide,
                "dose": dose_str,
                "timing": "late_evening",
            }

        # ── No spray needed
        reason = t.get("spray.moderate_wind_message") if wind_speed > 20 else t.get("spray.no_spray_message")
        return {
            "type": "SPRAY",
            "title": t.get("spray.no_spray_title"),
            "message": reason,
        }

    # ------------------------------------------------------------------
    # 2. FERTIGATION
    # ------------------------------------------------------------------
    def _decide_fertigation(
        self, crop: str, crop_kb: Dict, health_pct: float, ndvi: float,
        bbch_stage: int, soil_moisture: float, is_organic: bool,
        t: I18n,
    ) -> Dict:

        # ── Agronomic Safety: No fertigation during Ripening/Harvesting (BBCH 80+)
        if bbch_stage >= 80:
            return {
                "type": "FERTIGATION",
                "title": t.get("fertigation.ripening_title"),
                "message": t.get("fertigation.ripening_message"),
            }

        ndvi_threshold = crop_kb.get("ndvi_threshold_for_fertilize", 0.60)
        needs_fert = ndvi < ndvi_threshold or health_pct < 85

        if is_organic:
            if needs_fert:
                return {
                    "type": "FERTIGATION",
                    "title": t.get("fertigation.organic_needed_title"),
                    "message": t.get("fertigation.organic_needed_message",
                                     ndvi=f"{ndvi:.3f}", ndvi_threshold=f"{ndvi_threshold:.2f}",
                                     health=f"{health_pct:.0f}"),
                }
            return {
                "type": "FERTIGATION",
                "title": t.get("fertigation.organic_ok_title"),
                "message": t.get("fertigation.organic_ok_message"),
            }

        if needs_fert:
            nutrient = self._get_fertilizer_for_crop(crop, bbch_stage, crop_kb)
            dose_kg  = self._get_fertilizer_dose(nutrient, crop_kb)
            timing   = "tomorrow" if soil_moisture > 30 else "today_evening"
            return {
                "type": "FERTIGATION",
                "title": t.get("fertigation.inorganic_title"),
                "message": t.get("fertigation.inorganic_message",
                                  nutrient=nutrient, dose=dose_kg),
                "nutrient": nutrient,
                "dose": f"{dose_kg} kg/acre",
                "timing": timing,
            }

        return {
            "type": "FERTIGATION",
            "title": t.get("fertigation.none_title"),
            "message": t.get("fertigation.none_message",
                              ndvi=f"{ndvi:.3f}", ndvi_threshold=f"{ndvi_threshold:.2f}"),
        }

    # ------------------------------------------------------------------
    # 3. IRRIGATION
    # ------------------------------------------------------------------
    def _decide_irrigation(
        self, crop: str, crop_kb: Dict, soil_moisture: float,
        rainfall_forecast: float, irrigation_type: str, acre: float,
        water_stress_level: str, t: I18n,
    ) -> Dict:

        sm_critical = crop_kb.get("soil_moisture_critical", 35.0)
        ideal_range = crop_kb.get("ideal_range", "50-70%")
        method = irrigation_type or "Drip"

        # Severe water stress alert overrides everything
        if water_stress_level.lower() in ["high", "severe"]:
            return {
                "type": "IRRIGATION",
                "title": t.get("irrigation.stress_title"),
                "message": t.get("irrigation.stress_message",
                                  stress_level=water_stress_level.lower()),
                "method": method,
                "timing": "immediately",
            }

        if rainfall_forecast > 20:
            return {
                "type": "IRRIGATION",
                "title": t.get("irrigation.skip_rain_title"),
                "message": t.get("irrigation.skip_rain_message",
                                  rainfall=f"{rainfall_forecast:.0f}",
                                  soil_moisture=f"{soil_moisture:.0f}"),
            }

        if soil_moisture < sm_critical:
            water_hours = self._calculate_water_hours(soil_moisture, crop_kb)
            water_mm    = round(water_hours * 13)
            method      = irrigation_type or "Drip"
            return {
                "type": "IRRIGATION",
                "title": t.get("irrigation.needed_title"),
                "message": t.get("irrigation.needed_message",
                                  method=method, hours=f"{water_hours:.1f}",
                                  mm=water_mm, minutes=int(water_hours * 60)),
                "method": method,
                "water_hours": water_hours,
                "timing": "today_morning",
            }

        return {
            "type": "IRRIGATION",
            "title": t.get("irrigation.ok_title"),
            "message": t.get("irrigation.ok_message",
                              soil_moisture=f"{soil_moisture:.0f}",
                              ideal_range=ideal_range),
        }

    # ------------------------------------------------------------------
    # 4. WEATHER
    # ------------------------------------------------------------------
    def _decide_weather(
        self, temperature: float, humidity: float,
        rainfall_forecast: float, wind_speed: float,
        forecast: Optional[Dict[str, List[float]]] = None,
        t: I18n = None,
    ) -> Dict:
        if t is None:
            t = I18n("en")

        alerts = []
        if temperature > 35:
            alerts.append(t.get("weather.heat_today", temp=f"{temperature:.1f}"))
        if temperature < 5:
            alerts.append(t.get("weather.frost_today", temp=f"{temperature:.1f}"))
        if rainfall_forecast > 30:
            alerts.append(t.get("weather.heavy_rain", rainfall=f"{rainfall_forecast:.0f}"))
        if wind_speed > 30:
            alerts.append(t.get("weather.high_wind_today", wind=f"{wind_speed:.0f}"))
        if humidity > 85:
            alerts.append(t.get("weather.high_humidity", humidity=f"{humidity:.0f}"))

        # Check forecast arrays if provided
        if forecast:
            wind_forecast = forecast.get("wind_speed", [])
            if any(w > 40 for w in wind_forecast[:3]):
                day_idx = next(i for i, w in enumerate(wind_forecast[:3]) if w > 40)
                alerts.append(t.get("weather.forecast_wind", days=day_idx + 1))

            temp_max = forecast.get("temp_max", [])
            if any(tmp > 38 for tmp in temp_max[:5]):
                day_idx = next(i for i, tmp in enumerate(temp_max[:5]) if tmp > 38)
                alerts.append(t.get("weather.forecast_heatwave", days=day_idx + 1))

            temp_min = forecast.get("temp_min", [])
            if any(tmp < 4 for tmp in temp_min[:5]):
                day_idx = next(i for i, tmp in enumerate(temp_min[:5]) if tmp < 4)
                alerts.append(t.get("weather.forecast_frost", days=day_idx + 1))

        if alerts:
            title = t.get("weather.heat_alert_title") if temperature > 35 else t.get("weather.alert_title")
            return {
                "type": "WEATHER", "title": title,
                "message": " ".join(alerts),
            }

        return {
            "type": "WEATHER",
            "title": t.get("weather.update_title"),
            "message": t.get("weather.update_message",
                              temp=f"{temperature:.1f}", humidity=f"{humidity:.0f}",
                              wind=f"{wind_speed:.0f}"),
        }

    # ------------------------------------------------------------------
    # 5. CROP RISK
    # ------------------------------------------------------------------
    def _decide_crop_risk(
        self, crop: str, crop_kb: Dict, health_pct: float, ndvi: float,
        humidity: float, temperature: float, is_organic: bool,
        t: I18n,
    ) -> Dict:

        ndvi_threshold  = crop_kb.get("ndvi_threshold_for_spray", 0.65)
        crit_humidity   = crop_kb.get("critical_humidity", 75.0)
        fungal_temp_min = crop_kb.get("fungal_temp_min", 20.0)
        fungal_temp_max = crop_kb.get("fungal_temp_max", 28.0)
        diseases        = crop_kb.get("primary_fungal_disease", "Fungal diseases")
        pests           = crop_kb.get("primary_pest", "Common pests")

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
            msg = (
                t.get("crop_risk.high_organic_message", diseases=diseases, pests=pests)
                if is_organic
                else t.get("crop_risk.high_message", diseases=diseases, pests=pests)
            )
            title = t.get("crop_risk.high_title")
        elif risk_score >= 3:
            risk_level = "Medium"
            msg = t.get("crop_risk.medium_message", diseases=diseases)
            title = t.get("crop_risk.medium_title")
        else:
            risk_level = "Low"
            msg = t.get("crop_risk.low_message")
            title = t.get("crop_risk.low_title")

        return {
            "type": "CROP_RISK",
            "title": title,
            "message": msg,
            "risk_level": risk_level,
        }

    # ------------------------------------------------------------------
    # 6. MONITORING
    # ------------------------------------------------------------------
    def _decide_monitoring(
        self, crop: str, crop_kb: Dict, health_pct: float, ndvi: float,
        ndvi_trend: float, t: I18n,
    ) -> Dict:
        tips = []

        if ndvi_trend <= -0.05:
            tips.append(t.get("monitoring.ndvi_drop_urgent", ndvi_trend=f"{ndvi_trend:.3f}"))
        else:
            tips.append(t.get("monitoring.routine_check"))

        if health_pct < 70:
            tips.append(t.get("monitoring.low_health", health=f"{health_pct:.0f}"))
        if ndvi < 0.5:
            tips.append(t.get("monitoring.low_ndvi", ndvi=f"{ndvi:.3f}"))

        pests = crop_kb.get("primary_pest", "")
        if pests:
            tips.append(t.get("monitoring.watch_pest", pests=pests))

        diseases = crop_kb.get("primary_fungal_disease", "")
        if diseases:
            tips.append(t.get("monitoring.watch_disease", diseases=diseases))

        return {
            "type": "MONITORING",
            "title": t.get("monitoring.title"),
            "message": " ".join(tips),
        }

    # ------------------------------------------------------------------
    # 7. CARBON TRACKING
    # ------------------------------------------------------------------
    def _decide_carbon_tracking(
        self, emission: float, captured: float, net: float,
        t: I18n,
    ) -> Dict:
        if net < 0:
            balance_msg = t.get("carbon.positive_balance", amount=f"{abs(net):.1f}")
        else:
            balance_msg = t.get("carbon.negative_balance", amount=f"{net:.1f}")

        return {
            "type": "CARBON_TRACKING",
            "title": t.get("carbon.title"),
            "message": t.get("carbon.message",
                              emission=f"{emission:.1f}", captured=f"{captured:.1f}",
                              net=f"{net:.1f}", balance=balance_msg),
        }

    # ------------------------------------------------------------------
    # UNKNOWN CROP FALLBACK
    # ------------------------------------------------------------------
    def _unknown_crop_defaults(self, crop: str, language: str = "en") -> List[Dict]:
        """
        Returned when a crop is not found in the knowledge base even after
        alias resolution. Gives safe, generic guidance instead of crashing.
        Uses i18n so non-English users also get a translated response.
        """
        t = I18n(language)
        return [
            {
                "type": "SPRAY",
                "title": t.get("spray.no_spray_title"),
                "message": t.get("unknown.spray_message", crop=crop),
            },
            {
                "type": "FERTIGATION",
                "title": t.get("fertigation.none_title"),
                "message": t.get("unknown.fertigation_message", crop=crop),
            },
            {
                "type": "IRRIGATION",
                "title": t.get("irrigation.ok_title"),
                "message": t.get("unknown.irrigation_message", crop=crop),
            },
            {
                "type": "WEATHER",
                "title": t.get("weather.update_title"),
                "message": t.get("unknown.weather_message"),
            },
            {
                "type": "CROP_RISK",
                "title": t.get("unknown.crop_risk_title"),
                "message": t.get("unknown.crop_risk_message", crop=crop),
            },
            {
                "type": "MONITORING",
                "title": t.get("monitoring.title"),
                "message": t.get("unknown.monitoring_message"),
            },
            {
                "type": "CARBON_TRACKING",
                "title": t.get("carbon.title"),
                "message": t.get("unknown.carbon_message"),
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
