"""Cliente HTTP para a plataforma ThingSpeak (envio de dados de sensor).

Doc oficial: https://www.mathworks.com/help/thingspeak/writedata.html
O ThingSpeak aceita até 8 *fields* numéricos por canal; este projeto usa
``field1`` para temperatura e ``field2`` para umidade ao sincronizar.
"""
from __future__ import annotations

import requests

from ..config import Config

BASE_URL = "https://api.thingspeak.com/update.json"


def enviar_leitura_thingspeak(fields: dict) -> dict:
    """Envia uma leitura para um canal ThingSpeak.

    ``fields`` deve ser um dict com chaves ``field1`` .. ``field8``.
    Valores ``None`` são ignorados para não sobrescrever campos vazios.
    """
    if not Config.THINGSPEAK_WRITE_KEY:
        raise RuntimeError("THINGSPEAK_WRITE_KEY não configurada")

    payload = {"api_key": Config.THINGSPEAK_WRITE_KEY}
    payload.update({k: v for k, v in fields.items() if v is not None})

    try:
        resp = requests.post(BASE_URL, json=payload, timeout=10)
    except requests.RequestException as exc:
        raise RuntimeError(f"falha de rede ao enviar para ThingSpeak: {exc}") from exc

    if resp.status_code != 200:
        raise RuntimeError(f"ThingSpeak retornou {resp.status_code}: {resp.text}")

    # Quando o canal devolve apenas o entry_id em texto puro, embrulhamos em dict.
    try:
        return resp.json()
    except ValueError:
        return {"entry_id": resp.text.strip()}
