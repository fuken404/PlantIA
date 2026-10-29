#!/usr/bin/env python3
"""Simulador de sensor de PlantIA.

Envía una lectura realista por cada planta, como lo haría un ESP32:
- la temperatura sigue el ciclo del día en Bogotá (fría en la madrugada, cálida en la tarde);
- la humedad del suelo baja poco a poco y sube de golpe cuando "alguien riega".

Uso (solo librería estándar):
    PLANTIA_API_URL=https://plantia.fuken404.dev PLANTIA_DEVICE_KEY=... python simulator/simulate.py
"""

import json
import math
import os
import random
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BOGOTA = timezone(timedelta(hours=-5))


def request(method: str, url: str, body: dict | None = None, key: str | None = None) -> dict:
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['X-Device-Key'] = key
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def simulated_temperature(now: datetime, t_min: float, t_max: float) -> float:
    """Ciclo diario: mínimo hacia las 5 a. m. y máximo hacia las 3 p. m., hora de Bogotá."""
    hour = now.astimezone(BOGOTA).hour + now.minute / 60
    middle, amplitude = (t_min + t_max) / 2, (t_max - t_min) / 2.4
    return middle + amplitude * math.sin((hour - 9) / 24 * 2 * math.pi) + random.uniform(-0.6, 0.6)


def simulated_humidity(previous: float | None, h_min: float, h_max: float) -> float:
    if previous is None:
        return random.uniform(h_min + 5, h_max - 5)
    if previous < h_min - 6 and random.random() < 0.5:
        return random.uniform(h_max - 4, h_max + 6)  # riego
    return previous - random.uniform(0.6, 1.6)  # el suelo se seca de a poco


def main() -> int:
    base = os.environ.get('PLANTIA_API_URL', 'http://127.0.0.1:8000').rstrip('/')
    key = os.environ.get('PLANTIA_DEVICE_KEY')
    if not key:
        print('Falta PLANTIA_DEVICE_KEY', file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    for plant in request('GET', f'{base}/api/plants'):
        th = plant['thresholds']
        last = plant.get('last_reading') or {}
        reading = {
            'plant_id': plant['id'],
            'humidity': round(max(5, min(95, simulated_humidity(
                last.get('humidity'), th['humidity_min'], th['humidity_max']))), 1),
            'temperature': round(simulated_temperature(now, th['temperature_min'], th['temperature_max']), 1),
        }
        try:
            request('POST', f'{base}/api/readings', reading, key)
            print(f"{plant['id']}: {reading['humidity']}% · {reading['temperature']} °C")
        except urllib.error.HTTPError as error:
            print(f"{plant['id']}: error {error.code} {error.read().decode()[:200]}", file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
