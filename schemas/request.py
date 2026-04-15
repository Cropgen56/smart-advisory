from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class Geometry(BaseModel):
    type: str
    coordinates: List[Any]

class FarmField(BaseModel):
    cropName: str
    variety: Optional[str] = None
    sowingDate: str
    acre: float
    typeOfFarming: str
    typeOfIrrigation: str
    geometry: Optional[Geometry] = None

class CurrentWeather(BaseModel):
    temp: float
    relative_humidity: float
    precipitation: float
    wind_speed: float
    et0_fao_evapotranspiration: float
    soil_moisture_5cm: float
    soil_moisture_15cm: float

class ForecastWeather(BaseModel):
    time: List[str]
    temp_mean: List[float]
    temp_max: List[float]
    temp_min: List[float]
    precipitation: List[float]
    relative_humidity: List[float]
    evapotranspiration: List[float]
    wind_speed: List[float]

class WeatherData(BaseModel):
    current: CurrentWeather
    forecast: ForecastWeather

class NDVIData(BaseModel):
    ndviLatest: float
    ndviMean: float
    ndviTrend: float
    values: List[float]

class WaterData(BaseModel):
    waterLatest: float
    waterMean: float
    stressLevel: str
    confidence: float

class PlantGrowthActivity(BaseModel):
    bbchStage: int
    stageName: str
    description: str
    cumulativeGDD: float
    overallProgress: float
    stageProgress: float

class AdvisoryRequestSchema(BaseModel):
    farmField: FarmField
    language: str
    platform: str
    weather: WeatherData
    ndvi: NDVIData
    water: WaterData
    plantGrowthActivity: Optional[PlantGrowthActivity] = None