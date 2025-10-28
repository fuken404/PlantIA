"""
Backend API for plant health monitoring using the unofficial meta-ai-api library.

This version of the application uses the open-source `meta_ai_api` package,
which wraps the Meta AI web interface and does **not** require an API key.
It exposes a REST endpoint que obtiene la humedad y la temperatura desde un
documento en Firestore y consulta Meta AI para obtener consejos de cuidado.
La respuesta se espera como una cadena JSON y se analiza en consecuencia.

To run the API locally:

1. Install dependencies: `pip install fastapi uvicorn meta-ai-api firebase-admin python-dotenv`
2. Start the server: `uvicorn plant_monitor_app:app --reload`

Note: `meta_ai_api` no requiere clave API, pero depende de endpoints
internos de meta.ai que podrían cambiar. Si Meta libera una API oficial
para tu región, considera pasarte a `llama-api-client`. Para Firestore,
configura la variable de entorno `GOOGLE_APPLICATION_CREDENTIALS` apuntando
al archivo JSON de la cuenta de servicio con permisos de lectura (ruta
relativa a este archivo o absoluta).
"""

import asyncio
import json
import os
from typing import Any, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    from meta_ai_api import MetaAI
except ImportError as exc:
    raise ImportError(
        "The 'meta_ai_api' library is not installed. Run 'pip install meta-ai-api'"
    ) from exc

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError as exc:
    raise ImportError(
        "The 'firebase-admin' library is required to leer datos desde Firestore. "
        "Instálalo con 'pip install firebase-admin'."
    ) from exc

ai = MetaAI()

app = FastAPI(
    title="Smart Plant Monitor",
    description=(
        "API REST que utiliza el servicio meta.ai a través de la librería "
        "meta‑ai‑api para proporcionar consejos de cuidado de   plantas "
        "en función de lecturas de humedad y temperatura."
    ),
    version="1.0.0",
)


_firestore_client: Any | None = None


def get_firestore_client() -> firestore.Client:

    global _firestore_client

    if _firestore_client is not None:
        return _firestore_client

    try:
        firebase_admin.get_app()
    except ValueError:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path:
            if not os.path.isabs(cred_path):
                base_dir = os.path.dirname(os.path.abspath(__file__))
                cred_path = os.path.join(base_dir, cred_path)
            if not os.path.exists(cred_path):
                raise RuntimeError(
                    "El archivo de credenciales configurado en "
                    "GOOGLE_APPLICATION_CREDENTIALS no existe: "
                    f"{cred_path}"
                )
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()

    _firestore_client = firestore.client()
    return _firestore_client


def fetch_measurements(document_path: str) -> Tuple[float, float]:
    """Fetch humidity and temperature from the given Firestore document."""

    normalized_path = document_path.strip().strip("/")
    if not normalized_path:
        raise HTTPException(
            status_code=400,
            detail="El campo 'document_path' no puede estar vacío.",
        )

    client = get_firestore_client()
    snapshot = client.document(normalized_path).get()

    if not snapshot.exists:
        raise HTTPException(
            status_code=404,
            detail=f"El documento '{document_path}' no existe en Firestore.",
        )

    data = snapshot.to_dict() or {}

    try:
        humidity = float(data["humedad"])
        temperature = float(data["temperatura"])
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El documento '{document_path}' debe contener los campos "
                "'humedad' y 'temperatura'. No se encontró: "
                f"{exc.args[0]}"
            ),
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Los campos 'humedad' y 'temperatura' deben ser numéricos en Firestore. "
                f"Datos recibidos: {data}"
            ),
        ) from exc

    return humidity, temperature


# Pydantic model for the request payload
class PlantStatusRequest(BaseModel):
    document_path: str = Field(
        ...,
        description=(
            "Ruta completa del documento en Firestore que contiene los campos "
            "'humedad' y 'temperatura'."
        ),
        example="jardin/jardin/Maycol/Rositas",
    )


# Pydantic model for the response payload
class PlantAdviceResponse(BaseModel):
    needs_watering: bool
    needs_soil: bool
    comment: str


@app.post("/plant-status", response_model=PlantAdviceResponse)
async def get_plant_status(payload: PlantStatusRequest) -> PlantAdviceResponse:
    humidity, temperature = await asyncio.to_thread(
        fetch_measurements, payload.document_path
    )

    prompt = (
        "Eres un experto en cuidado de plantas. Responderás en español y "
        "proporcionarás recomendaciones específicas basadas en los datos de humedad "
        "y temperatura que recibes. La respuesta debe ser un objeto JSON con las "
        "claves 'needs_watering', 'needs_soil', 'needs_light' y 'comment'. "
        "No incluyas ningún texto fuera del JSON. "
        f"La planta tiene una humedad de {humidity:.1f}% y una temperatura de "
        f"{temperature:.1f} °C. Indica si necesita riego, más tierra o más luz."
    )

    try:
        raw = ai.prompt(message=prompt)
        # Si la respuesta es un diccionario con clave 'message', extraemos el JSON
        if isinstance(raw, dict):
            if all(k in raw for k in ("needs_watering", "needs_soil", "comment")):
                advice_data = raw  # ya tenemos el dict final
            elif "message" in raw:
                response_str = raw["message"]
                advice_data = json.loads(response_str)
            else:
                raise ValueError(f"Estructura desconocida: {raw}")
        else:
            # Si es una cadena JSON, la parseamos
            advice_data = json.loads(raw)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener o analizar la respuesta de Meta AI: {e}",
        )

    try:
        return PlantAdviceResponse(**advice_data)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"La respuesta de Meta AI no tiene la estructura esperada: {e}",
        )
