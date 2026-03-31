from pydantic import BaseModel, Field
from typing import List, Optional

class PlateResult(BaseModel):
    plate: str
    state: str
    make: str
    model: str
    color: str
    vin: Optional[str] = ""
    match: Optional[str] = ""
    confidence: float
    edge_flags: List[str] = []

class JobStats(BaseModel):
    total_unique_plates: int = 0
    cost_total_gemini: float = 0.0
    run_elapsed_seconds: float = 0.0

class JobResponse(BaseModel):
    id: str
    status: str
    stats: Optional[JobStats] = None
    results: Optional[List[PlateResult]] = None
    inserted_sighting_ids: Optional[List[str]] = None
