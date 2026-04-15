

from pydantic import BaseModel, Field
from typing import List, Optional

class CropHealth(BaseModel):
    category: str
    percentage: float
    recommendation: str

class YieldPrediction(BaseModel):
    standardYield: float
    aiYield: float
    unit: str
    explanation: str

class CarbonData(BaseModel):
    emissionKgCO2: float
    capturedKgCO2: float
    netBalanceKgCO2: float

class ActivityToDo(BaseModel):
    type: str
    title: str
    message: str

class PlantGrowthResponse(BaseModel):
    stageName: str
    bbchStage: int
    cumulativeGDD: float
    overallProgress: float

class AdvisoryResponseSchema(BaseModel):
    success: bool
    message: Optional[str] = None
    plantGrowthActivity: Optional[PlantGrowthResponse] = None
    cropHealth: Optional[CropHealth] = None
    yield_data: Optional[YieldPrediction] = Field(None, serialization_alias="yield")
    carbonData: Optional[CarbonData] = None
    activitiesToDo: List[ActivityToDo] = []
    
    class Config:
        populate_by_name = True