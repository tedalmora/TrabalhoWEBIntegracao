"""Cliente HTTP para a API OpenWeatherMap.

Documentação oficial: https://openweathermap.org/current
A função devolve um dict **já normalizado** — a rota não precisa
conhecer a estrutura crua do JSON original.
"""
from __future__ import annotations

import requests

from ..config import Config

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


def obter_clima(cidade: str) -> dict:
    """Consulta o clima atual para uma cidade.

    Retorna um dict normalizado::

        {
          "cidade": "Curitiba",
          "pais": "BR",
          "temperatura": 22.5,
          "sensacao": 21.9,
          "umidade": 78,
          "descricao": "céu limpo",
          "vento_ms": 3.5
        }

    Lança :class:`RuntimeError` para que a rota traduza em HTTP 502.
    """
    # Falha cedo se a aplicação não foi configurada com a chave da API.
    if not Config.OPENWEATHER_API_KEY:
        raise RuntimeError("OPENWEATHER_API_KEY não configurada")

    params = {
        "q": cidade,
        "appid": Config.OPENWEATHER_API_KEY,
        "units": "metric",   # Celsius
        "lang": "pt_br",
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
    except requests.RequestException as exc:
        raise RuntimeError(f"falha de rede ao consultar OpenWeatherMap: {exc}") from exc

    if resp.status_code != 200:
        raise RuntimeError(f"OpenWeatherMap retornou {resp.status_code}: {resp.text}")

    data = resp.json()
    # ``.get`` em cadeia evita KeyError quando algum campo opcional vier ausente.
    return {
        "cidade": data.get("name"),
        "pais": (data.get("sys") or {}).get("country"),
        "temperatura": (data.get("main") or {}).get("temp"),
        "sensacao": (data.get("main") or {}).get("feels_like"),
        "umidade": (data.get("main") or {}).get("humidity"),
        "descricao": ((data.get("weather") or [{}])[0]).get("description"),
        "vento_ms": (data.get("wind") or {}).get("speed"),
    }
