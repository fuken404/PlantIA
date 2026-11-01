import os
import secrets
from datetime import timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .advisor import FallbackAdvisor, GeminiAdvisor, RulesAdvisor
from .config import Settings, get_settings
from .schemas import Advice, Plant, PlantStatus, Reading, ReadingIn
from .store import DEMO_PLANTS, FirestoreStore, MemoryStore, PlantStore, history_start, utcnow

app = FastAPI(
    title='PlantIA',
    description='Monitoreo de plantas: lecturas de sensores y consejos de cuidado generados con IA.',
    version='2.0.0',
    docs_url='/api/docs',
    redoc_url=None,
    openapi_url='/api/openapi.json',
)


@lru_cache
def get_store() -> PlantStore:
    settings = get_settings()
    if settings.storage == 'memory':
        return MemoryStore()
    if not settings.firebase_credentials_json:
        raise RuntimeError('Falta FIREBASE_CREDENTIALS_JSON (o usa STORAGE=memory para desarrollo).')
    store = FirestoreStore(settings.firebase_credentials_json)
    store.seed(DEMO_PLANTS)  # crea las plantas de ejemplo solo si no existen
    return store


@lru_cache
def get_advisor() -> FallbackAdvisor:
    settings = get_settings()
    gemini = None
    if settings.gemini_api_key:
        gemini = GeminiAdvisor(settings.gemini_api_key, settings.gemini_model, settings.gemini_timeout_seconds)
    return FallbackAdvisor(primary=gemini, fallback=RulesAdvisor())


StoreDep = Annotated[PlantStore, Depends(get_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def require_device(settings: SettingsDep, x_device_key: Annotated[str | None, Header()] = None) -> None:
    if not settings.device_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, 'El registro de lecturas no está configurado.')
    if not x_device_key or not secrets.compare_digest(x_device_key, settings.device_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Llave de dispositivo inválida.')


def current_advice(plant: Plant, store: PlantStore, advisor: FallbackAdvisor,
                   settings: Settings, history: list[Reading]) -> Advice | None:
    """Reutiliza el último consejo mientras sea reciente; si no, genera uno nuevo.

    Un consejo de respaldo por reglas solo vale para su lectura: con la siguiente se reintenta Gemini.
    """
    reading = plant.last_reading
    if reading is None:
        return None
    cached = store.get_advice(plant.id)
    if cached and (
        cached.reading_at >= reading.recorded_at
        or (cached.source != 'rules' and utcnow() - cached.generated_at < timedelta(minutes=settings.advice_ttl_minutes))
    ):
        return cached
    content, source = advisor.advise(plant, reading, history)
    advice = Advice(**content.model_dump(), source=source, generated_at=utcnow(), reading_at=reading.recorded_at)
    store.save_advice(plant.id, advice)
    return advice


@app.get('/api/health', tags=['sistema'])
def health():
    return {'status': 'ok'}


@app.get('/api/plants', response_model=list[Plant], tags=['plantas'])
def list_plants(store: StoreDep):
    return store.list_plants()


@app.get('/api/plants/{plant_id}', response_model=PlantStatus, tags=['plantas'])
def plant_status(plant_id: str, store: StoreDep, settings: SettingsDep,
                 advisor: Annotated[FallbackAdvisor, Depends(get_advisor)]):
    plant = store.get_plant(plant_id)
    if plant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Planta no encontrada.')
    history = store.readings_since(plant_id, history_start(settings.history_hours))
    advice = current_advice(plant, store, advisor, settings, history)
    return PlantStatus(plant=plant, readings=history, advice=advice)


@app.post('/api/readings', status_code=status.HTTP_201_CREATED, response_model=Reading,
          dependencies=[Depends(require_device)], tags=['lecturas'])
def add_reading(data: ReadingIn, store: StoreDep):
    if store.get_plant(data.plant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Planta no encontrada.')
    reading = Reading(humidity=data.humidity, temperature=data.temperature, recorded_at=utcnow())
    store.add_reading(data.plant_id, reading)
    return reading


# En Vercel el panel (public/) se sirve desde la CDN. En local lo servimos aquí.
if not os.getenv('VERCEL'):
    from fastapi.staticfiles import StaticFiles

    app.mount('/', StaticFiles(directory='public', html=True), name='panel')
