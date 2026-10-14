from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from normalizer.G2_26_discrepancy_classifier import DiscrepancyClassifier

app = FastAPI()
classifier = DiscrepancyClassifier()

class DiffPayload(BaseModel):
    path: str
    message: str
    category: Optional[str] = None

@app.post("/classify")
def classify_discrepancy(payload: DiffPayload):
    label = classifier.classify(payload.model_dump())
    return {"category": label}