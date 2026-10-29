"""Almacenamiento de plantas y lecturas.

Firestore guarda:
    plants/{id}                 nombre, especie, rangos, última lectura y último consejo
    plants/{id}/readings/{auto} historial de lecturas
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .schemas import Advice, Plant, Reading, Thresholds

DEMO_PLANTS = [
    Plant(
        id='rosita', name='Rosita', species='Rosa chinensis',
        thresholds=Thresholds(humidity_min=40, humidity_max=70, temperature_min=15, temperature_max=28),
    ),
    Plant(
        id='monstera', name='Monstera', species='Monstera deliciosa',
        thresholds=Thresholds(humidity_min=35, humidity_max=65, temperature_min=18, temperature_max=30),
    ),
]


class PlantStore(Protocol):
    def list_plants(self) -> list[Plant]: ...
    def get_plant(self, plant_id: str) -> Plant | None: ...
    def add_reading(self, plant_id: str, reading: Reading) -> None: ...
    def readings_since(self, plant_id: str, since: datetime) -> list[Reading]: ...
    def get_advice(self, plant_id: str) -> Advice | None: ...
    def save_advice(self, plant_id: str, advice: Advice) -> None: ...


class MemoryStore:
    """Datos en memoria: para desarrollo local y pruebas."""

    def __init__(self, plants: list[Plant] | None = None):
        self._plants = {p.id: p.model_copy(deep=True) for p in (plants or DEMO_PLANTS)}
        self._readings: dict[str, list[Reading]] = {pid: [] for pid in self._plants}
        self._advice: dict[str, Advice] = {}

    def list_plants(self):
        return list(self._plants.values())

    def get_plant(self, plant_id):
        return self._plants.get(plant_id)

    def add_reading(self, plant_id, reading):
        self._readings[plant_id].append(reading)
        self._plants[plant_id].last_reading = reading

    def readings_since(self, plant_id, since):
        return [r for r in self._readings.get(plant_id, []) if r.recorded_at >= since]

    def get_advice(self, plant_id):
        return self._advice.get(plant_id)

    def save_advice(self, plant_id, advice):
        self._advice[plant_id] = advice


class FirestoreStore:
    def __init__(self, credentials_json: str):
        # Importaciones locales: el modo memoria no necesita las librerías de Google.
        from google.cloud import firestore
        from google.oauth2 import service_account

        info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(info)
        self._db = firestore.Client(project=info['project_id'], credentials=credentials)

    def _plant_from_doc(self, doc) -> Plant:
        data = doc.to_dict()
        return Plant(id=doc.id, **{k: v for k, v in data.items() if k in Plant.model_fields})

    def list_plants(self):
        return [self._plant_from_doc(d) for d in self._db.collection('plants').order_by('name').stream()]

    def get_plant(self, plant_id):
        doc = self._db.collection('plants').document(plant_id).get()
        return self._plant_from_doc(doc) if doc.exists else None

    def add_reading(self, plant_id, reading):
        plant_ref = self._db.collection('plants').document(plant_id)
        batch = self._db.batch()
        batch.set(plant_ref.collection('readings').document(), reading.model_dump())
        batch.update(plant_ref, {'last_reading': reading.model_dump()})
        batch.commit()

    def readings_since(self, plant_id, since):
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = (
            self._db.collection('plants').document(plant_id).collection('readings')
            .where(filter=FieldFilter('recorded_at', '>=', since))
            .order_by('recorded_at')
            .limit(500)
        )
        return [Reading(**d.to_dict()) for d in query.stream()]

    def get_advice(self, plant_id):
        doc = self._db.collection('plants').document(plant_id).get()
        data = (doc.to_dict() or {}).get('advice') if doc.exists else None
        return Advice(**data) if data else None

    def save_advice(self, plant_id, advice):
        self._db.collection('plants').document(plant_id).update({'advice': advice.model_dump()})

    def seed(self, plants: list[Plant]) -> int:
        """Crea las plantas que no existan (no toca las existentes)."""
        created = 0
        for plant in plants:
            ref = self._db.collection('plants').document(plant.id)
            if not ref.get().exists:
                ref.set(plant.model_dump(exclude={'id', 'last_reading'}))
                created += 1
        return created


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def history_start(hours: int) -> datetime:
    return utcnow() - timedelta(hours=hours)
