"""Consejos de cuidado: Gemini con respaldo por reglas."""

import logging
from typing import Protocol

from .schemas import AdviceContent, Plant, Reading

logger = logging.getLogger(__name__)


class Advisor(Protocol):
    source: str

    def advise(self, plant: Plant, reading: Reading, history: list[Reading]) -> AdviceContent: ...


class RulesAdvisor:
    """Compara la lectura con los rangos ideales de la planta."""

    source = 'rules'

    def advise(self, plant, reading, history):
        t = plant.thresholds
        dry = reading.humidity < t.humidity_min
        soaked = reading.humidity > t.humidity_max
        cold = reading.temperature < t.temperature_min
        hot = reading.temperature > t.temperature_max

        very_dry = reading.humidity < t.humidity_min - 15
        extreme_temp = reading.temperature < t.temperature_min - 5 or reading.temperature > t.temperature_max + 5
        if very_dry or extreme_temp:
            status = 'critical'
        elif dry or soaked or cold or hot:
            status = 'attention'
        else:
            status = 'healthy'

        es, en = [], []
        if dry:
            es.append('El suelo está seco: riégala hoy.')
            en.append('The soil is dry: water it today.')
        elif soaked:
            es.append('Hay exceso de agua: deja secar la tierra antes de volver a regar.')
            en.append('The soil is waterlogged: let it dry out before watering again.')
        if cold:
            es.append('Hace frío para ella: aléjala de corrientes de aire.')
            en.append('It is too cold for it: keep it away from drafts.')
        elif hot:
            es.append('Hace calor: protégela del sol directo de mediodía.')
            en.append('It is too hot: shield it from direct midday sun.')
        if not es:
            es.append('Todo en orden: humedad y temperatura dentro del rango ideal.')
            en.append('All good: moisture and temperature are within the ideal range.')

        return AdviceContent(
            status=status, needs_watering=dry, temperature_ok=not (cold or hot),
            tip_es=' '.join(es), tip_en=' '.join(en),
        )


class GeminiAdvisor:
    source = 'gemini'

    SYSTEM = (
        'Eres un agrónomo que cuida plantas de interior. Recibes la lectura actual de un sensor '
        '(humedad del suelo y temperatura), el historial reciente y los rangos ideales de la planta. '
        'Responde solo con el JSON pedido. Los consejos deben ser concretos, accionables y de máximo '
        'dos frases; no inventes datos que no estén en la lectura.'
    )

    def __init__(self, api_key: str, model: str, timeout_seconds: int):
        from google import genai
        from google.genai import types

        self._types = types
        self._model = model
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=timeout_seconds * 1000),
        )

    def advise(self, plant, reading, history):
        t = plant.thresholds
        if history:
            hums = [r.humidity for r in history]
            temps = [r.temperature for r in history]
            trend = (
                f'Últimas {len(history)} lecturas: humedad entre {min(hums):.0f}% y {max(hums):.0f}%, '
                f'temperatura entre {min(temps):.1f} y {max(temps):.1f} °C.'
            )
        else:
            trend = 'Sin historial reciente.'
        prompt = (
            f'Planta: {plant.name} ({plant.species}).\n'
            f'Rango ideal: humedad {t.humidity_min:.0f}-{t.humidity_max:.0f}%, '
            f'temperatura {t.temperature_min:.0f}-{t.temperature_max:.0f} °C.\n'
            f'Lectura actual: humedad {reading.humidity:.1f}%, temperatura {reading.temperature:.1f} °C.\n'
            f'{trend}'
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                system_instruction=self.SYSTEM,
                response_mime_type='application/json',
                response_schema=AdviceContent,
                temperature=0.4,
                max_output_tokens=400,
            ),
        )
        return AdviceContent.model_validate_json(response.text)


class FallbackAdvisor:
    """Usa el asesor principal y, si falla, las reglas. Informa cuál respondió."""

    def __init__(self, primary: Advisor | None, fallback: Advisor):
        self.primary = primary
        self.fallback = fallback

    def advise(self, plant, reading, history) -> tuple[AdviceContent, str]:
        if self.primary is not None:
            try:
                return self.primary.advise(plant, reading, history), self.primary.source
            except Exception:
                logger.exception('El asesor %s falló; se usa el respaldo por reglas', self.primary.source)
        return self.fallback.advise(plant, reading, history), self.fallback.source
