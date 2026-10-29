from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PlantId = Field(pattern=r'^[a-z0-9-]{1,40}$', description='Identificador de la planta, ej. "rosita"')


class ReadingIn(BaseModel):
    """Lectura enviada por un sensor."""

    plant_id: str = PlantId
    humidity: float = Field(ge=0, le=100, description='Humedad del suelo en %')
    temperature: float = Field(ge=-20, le=60, description='Temperatura ambiente en °C')


class Reading(BaseModel):
    humidity: float
    temperature: float
    recorded_at: datetime


class Thresholds(BaseModel):
    """Rangos ideales de la planta."""

    humidity_min: float
    humidity_max: float
    temperature_min: float
    temperature_max: float


class Plant(BaseModel):
    id: str
    name: str
    species: str
    thresholds: Thresholds
    last_reading: Reading | None = None


class AdviceContent(BaseModel):
    """Lo que debe devolver el modelo de IA (también lo produce el respaldo por reglas)."""

    status: Literal['healthy', 'attention', 'critical']
    needs_watering: bool
    temperature_ok: bool
    tip_es: str = Field(description='Consejo breve en español, máximo dos frases')
    tip_en: str = Field(description='El mismo consejo en inglés')


class Advice(AdviceContent):
    source: Literal['gemini', 'rules']
    generated_at: datetime
    # Lectura sobre la que se generó, para saber cuándo hace falta uno nuevo.
    reading_at: datetime


class PlantStatus(BaseModel):
    plant: Plant
    readings: list[Reading]
    advice: Advice | None
