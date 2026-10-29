# PlantIA

Monitoreo de plantas de interior: un sensor mide la **humedad del suelo** y la **temperatura**,
una API en **FastAPI** guarda las lecturas en **Firestore** y **Gemini** genera un consejo de
cuidado para cada planta. Si la IA no responde, un asesor por reglas toma su lugar, así que el
panel nunca queda sin respuesta.

**Demo:** [plantia.fuken404.dev](https://plantia.fuken404.dev) · **API:** [`/api/docs`](https://plantia.fuken404.dev/api/docs)

```
ESP32 o simulador ──POST /api/readings──► FastAPI (Vercel) ──► Firestore
   (cada 30 min)      X-Device-Key            │
                                              ├──► Gemini: consejo de cuidado
Panel web ◄────────GET /api/plants/{id}───────┘     (respaldo por reglas)
```

## Qué hay en el repo

| Carpeta | Contenido |
| --- | --- |
| `app/` | API: rutas (`main.py`), modelos (`schemas.py`), almacenamiento en Firestore o memoria (`store.py`) y asesores Gemini / reglas (`advisor.py`) |
| `public/` | Panel web sin dependencias (HTML, CSS y JS), en español e inglés |
| `simulator/` | Simulador de sensor: ciclo diario de temperatura en Bogotá y suelo que se seca hasta el próximo riego |
| `firmware/esp32/` | Firmware de referencia para ESP32 con sensor capacitivo de suelo y DHT22 |
| `tests/` | Pruebas de la API con almacenamiento en memoria y un Gemini falso |
| `.github/workflows/` | Pruebas en cada push y simulador programado cada 30 minutos |

## API

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/api/health` | Estado del servicio |
| `GET` | `/api/plants` | Plantas con su última lectura |
| `GET` | `/api/plants/{id}` | Lecturas de las últimas 24 h y consejo de cuidado |
| `POST` | `/api/readings` | Registra una lectura (requiere `X-Device-Key`) |

```bash
curl -X POST https://plantia.fuken404.dev/api/readings \
  -H "Content-Type: application/json" -H "X-Device-Key: $DEVICE_API_KEY" \
  -d '{"plant_id": "rosita", "humidity": 48.5, "temperature": 22.1}'
```

Decisiones de diseño:

- **El consejo se guarda en caché** junto a la planta y solo se regenera cuando hay una lectura
  nueva y pasó `ADVICE_TTL_MINUTES` (60 por defecto). Así el panel responde rápido y la cuota
  gratuita de Gemini alcanza.
- **Salida estructurada:** Gemini responde con un esquema JSON fijo (`status`, `needs_watering`,
  `temperature_ok`, `tip_es`, `tip_en`) que Pydantic valida antes de guardarlo.
- **Escritura autenticada:** solo quien tiene la llave del dispositivo puede registrar lecturas;
  la comparación es de tiempo constante. Firestore queda en modo producción (sin acceso desde el
  navegador) y solo el backend lo usa con su cuenta de servicio.

## Correr en local

No necesitas Firebase ni Gemini: con `STORAGE=memory` la app usa dos plantas de ejemplo en
memoria y los consejos salen del asesor por reglas.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

En otra terminal, genera lecturas:

```bash
PLANTIA_API_URL=http://127.0.0.1:8000 PLANTIA_DEVICE_KEY=clave-local-de-prueba python simulator/simulate.py
```

Abre http://127.0.0.1:8000. Pruebas: `pytest`.

## Despliegue (Vercel)

Vercel detecta la app de FastAPI en `app/main.py` y sirve `public/` desde su CDN.
Variables de entorno del proyecto:

| Variable | Descripción |
| --- | --- |
| `FIREBASE_CREDENTIALS_JSON` | JSON completo de la cuenta de servicio de Firebase |
| `GEMINI_API_KEY` | Llave de Google AI Studio |
| `DEVICE_API_KEY` | Llave que usan el sensor y el simulador |
| `GEMINI_MODEL` | Opcional, por defecto `gemini-3.5-flash-lite` |

Al primer arranque se crean en Firestore las plantas de ejemplo si no existen.
El workflow **Simulador de sensor** necesita los secretos `PLANTIA_API_URL` y `PLANTIA_DEVICE_KEY`
en el repositorio.

## Hardware (opcional)

`firmware/esp32/plantia.ino` lee un sensor capacitivo de humedad de suelo (GPIO 34) y un DHT22
(GPIO 4) y publica cada 30 minutos por HTTPS. Copia `secrets.example.h` como `secrets.h`,
completa tu red, la URL, la llave del dispositivo y el certificado raíz, y calibra
`SOIL_DRY` / `SOIL_WET` midiendo el sensor en aire y en agua.
