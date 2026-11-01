import os

os.environ['STORAGE'] = 'memory'
os.environ['DEVICE_API_KEY'] = 'llave-de-prueba'
os.environ['GEMINI_API_KEY'] = ''

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.advisor import FallbackAdvisor, RulesAdvisor  # noqa: E402
from app.main import app, get_advisor, get_store  # noqa: E402
from app.schemas import AdviceContent  # noqa: E402
from app.store import MemoryStore  # noqa: E402

DEVICE = {'X-Device-Key': 'llave-de-prueba'}


class FakeGemini:
    source = 'gemini'

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def advise(self, plant, reading, history):
        self.calls += 1
        if self.fail:
            raise RuntimeError('cuota agotada')
        return AdviceContent(status='healthy', needs_watering=False, temperature_ok=True,
                             tip_es='Todo bien.', tip_en='All good.')


@pytest.fixture
def client():
    store = MemoryStore()
    gemini = FakeGemini()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_advisor] = lambda: FallbackAdvisor(gemini, RulesAdvisor())
    with TestClient(app) as c:
        c.gemini = gemini
        yield c
    app.dependency_overrides.clear()


def send(client, plant_id='rosita', humidity=55, temperature=22, headers=DEVICE):
    return client.post('/api/readings', json={'plant_id': plant_id, 'humidity': humidity,
                                              'temperature': temperature}, headers=headers)


def test_health(client):
    assert client.get('/api/health').json() == {'status': 'ok'}


def test_lista_plantas_de_ejemplo(client):
    ids = [p['id'] for p in client.get('/api/plants').json()]
    assert ids == ['rosita', 'monstera']


def test_lectura_requiere_llave(client):
    assert send(client, headers={}).status_code == 401
    assert send(client, headers={'X-Device-Key': 'otra'}).status_code == 401


def test_lectura_valida_rangos(client):
    assert send(client, humidity=150).status_code == 422
    assert send(client, plant_id='No Valida').status_code == 422


def test_lectura_de_planta_inexistente(client):
    assert send(client, plant_id='cactus').status_code == 404


def test_estado_sin_lecturas_no_pide_consejo(client):
    data = client.get('/api/plants/rosita').json()
    assert data['readings'] == [] and data['advice'] is None
    assert client.gemini.calls == 0


def test_estado_con_lectura_genera_consejo(client):
    assert send(client).status_code == 201
    data = client.get('/api/plants/rosita').json()
    assert data['plant']['last_reading']['humidity'] == 55
    assert len(data['readings']) == 1
    assert data['advice']['source'] == 'gemini'


def test_consejo_se_reutiliza_dentro_del_ttl(client):
    send(client)
    client.get('/api/plants/rosita')
    send(client, humidity=50)
    client.get('/api/plants/rosita')
    assert client.gemini.calls == 1


def test_tras_un_fallo_se_reintenta_gemini_con_la_siguiente_lectura(client):
    client.gemini.fail = True
    send(client)
    assert client.get('/api/plants/rosita').json()['advice']['source'] == 'rules'
    client.gemini.fail = False
    send(client, humidity=50)
    assert client.get('/api/plants/rosita').json()['advice']['source'] == 'gemini'


def test_si_gemini_falla_responde_con_reglas(client):
    client.gemini.fail = True
    send(client, humidity=20)
    advice = client.get('/api/plants/rosita').json()['advice']
    assert advice['source'] == 'rules'
    assert advice['needs_watering'] is True
    assert advice['status'] == 'critical'


def test_planta_inexistente(client):
    assert client.get('/api/plants/cactus').status_code == 404


def test_reglas_cubren_frio_y_exceso_de_agua():
    plant = MemoryStore().get_plant('monstera')
    from app.schemas import Reading
    from app.store import utcnow
    content = RulesAdvisor().advise(plant, Reading(humidity=80, temperature=10, recorded_at=utcnow()), [])
    assert content.status == 'critical'
    assert content.temperature_ok is False and content.needs_watering is False
    assert 'agua' in content.tip_es and 'cold' in content.tip_en
