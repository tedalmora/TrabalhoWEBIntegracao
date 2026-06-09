"""Testes da API usando o test client do Flask.

Por padrão usam o backend **in-memory** (``USE_INMEMORY_DB=1``), então
rodam sem precisar de HBase nem Docker.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Garante que o pacote ``app`` seja importável quando pytest é chamado
# diretamente, sem instalação via ``pip install -e .``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Força o backend em memória **antes** de importar a app.
os.environ["USE_INMEMORY_DB"] = "1"
os.environ.setdefault("HBASE_TABLE_PREFIX", "iot_test")

from app import create_app  # noqa: E402
from app.database_inmemory import reset as reset_inmemory  # noqa: E402


@pytest.fixture()
def client():
    """Cliente de teste isolado: zera o banco em memória entre testes."""
    reset_inmemory()
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------
# Endpoints básicos
# ---------------------------------------------------------------------
def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "endpoints" in resp.get_json()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["api"] == "ok"
    assert body["banco"] == "ok"  # in-memory está sempre OK


# ---------------------------------------------------------------------
# Requisito 2 + 3 + 5 (sensores)
# ---------------------------------------------------------------------
def test_fluxo_sensor(client):
    novo = client.post("/sensores", json={"tipo": "temperatura", "localizacao": "Lab"})
    assert novo.status_code == 201
    sid = novo.get_json()["id"]

    # busca por chave (Req. 3)
    obtido = client.get(f"/sensores/{sid}")
    assert obtido.status_code == 200
    assert obtido.get_json()["tipo"] == "temperatura"

    # envio de leitura
    leit = client.post(f"/sensores/{sid}/dados", json={"valor": 25.4, "unidade": "C"})
    assert leit.status_code == 201

    # lista com filtro (Req. 5)
    listagem = client.get("/sensores?tipo=temperatura")
    assert listagem.status_code == 200
    ids = [s["id"] for s in listagem.get_json()["itens"]]
    assert sid in ids

    # filtro por faixa de valores
    leituras = client.get(f"/leituras?sensor_id={sid}&valor_min=20")
    assert leituras.status_code == 200
    assert leituras.get_json()["total"] >= 1


# ---------------------------------------------------------------------
# Requisito 2 (atuadores — envio de comando + status)
# ---------------------------------------------------------------------
def test_comando_atuador_sucesso(client):
    novo = client.post("/atuadores", json={"nome": "Lamp", "tipo": "lampada"})
    aid = novo.get_json()["id"]
    cmd = client.post(f"/atuadores/{aid}/comando", json={"comando": "LIGAR"})
    assert cmd.status_code == 200
    body = cmd.get_json()
    assert body["status"] == "sucesso"
    assert body["estado_atual"] == "LIGADO"


def test_comando_atuador_invalido(client):
    novo = client.post("/atuadores", json={"nome": "Lamp", "tipo": "lampada"})
    aid = novo.get_json()["id"]
    cmd = client.post(f"/atuadores/{aid}/comando", json={"comando": "EXPLODIR"})
    assert cmd.status_code == 400
    assert cmd.get_json()["status"] == "falha"


def test_comando_atuador_inexistente(client):
    cmd = client.post("/atuadores/nao_existe/comando", json={"comando": "LIGAR"})
    assert cmd.status_code == 404
    assert cmd.get_json()["status"] == "falha"


# ---------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------
def test_sensor_inexistente(client):
    resp = client.get("/sensores/nao_existe")
    assert resp.status_code == 404


def test_leitura_sem_valor(client):
    novo = client.post("/sensores", json={"tipo": "x", "localizacao": "y"}).get_json()
    resp = client.post(f"/sensores/{novo['id']}/dados", json={})
    assert resp.status_code == 400
