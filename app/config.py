from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración por variables de entorno (ver .env.example)."""

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    # 'memory' permite correr la app sin Firebase (datos de ejemplo en memoria).
    storage: Literal['firestore', 'memory'] = 'firestore'
    # Contenido completo del JSON de la cuenta de servicio de Firebase.
    firebase_credentials_json: str = ''

    gemini_api_key: str = ''
    gemini_model: str = 'gemini-3.5-flash-lite'
    gemini_timeout_seconds: int = 15

    # Llave con la que el sensor o el simulador publican lecturas.
    device_api_key: str = ''

    # Un consejo se reutiliza este tiempo antes de pedirle uno nuevo a Gemini.
    advice_ttl_minutes: int = 60
    history_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
