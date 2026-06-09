"""Popula o HBase com sensores, atuadores e leituras de exemplo.

Uso:

    python -m scripts.seed_data
"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Config  # noqa: E402
from app.database import connection  # noqa: E402
from app.utils.helpers import agora_ms, to_bytes_map  # noqa: E402


SENSORES = [
    ("sen_temp_01", {"tipo": "temperatura", "localizacao": "Sala 101", "descricao": "DHT22"}),
    ("sen_temp_02", {"tipo": "temperatura", "localizacao": "Sala 102", "descricao": "DHT22"}),
    ("sen_umid_01", {"tipo": "umidade",     "localizacao": "Sala 101", "descricao": "DHT22"}),
    ("sen_lum_01",  {"tipo": "luminosidade","localizacao": "Corredor", "descricao": "LDR"}),
]

ATUADORES = [
    ("atu_lamp_01", {"nome": "Lâmpada Sala 101", "tipo": "lampada", "localizacao": "Sala 101"}),
    ("atu_vent_01", {"nome": "Ventilador",       "tipo": "ventilador", "localizacao": "Sala 102"}),
]


def main() -> None:
    with connection() as conn:
        sensores = conn.table(Config.table("sensores"))
        atuadores = conn.table(Config.table("atuadores"))
        leituras  = conn.table(Config.table("leituras"))

        for sid, info in SENSORES:
            info = {**info, "criado_em": agora_ms()}
            sensores.put(sid.encode(), to_bytes_map("info", info))
            print(f"[sensor]   {sid}")

        for aid, info in ATUADORES:
            info_full = {**info, "criado_em": agora_ms()}
            sensores_bytes = {
                **to_bytes_map("info", info_full),
                **to_bytes_map("estado", {"atual": "DESLIGADO", "atualizado_em": agora_ms()}),
            }
            atuadores.put(aid.encode(), sensores_bytes)
            print(f"[atuador]  {aid}")

        for sid, _ in SENSORES:
            for _ in range(10):
                ts = agora_ms()
                valor = round(random.uniform(15.0, 35.0), 2)
                row_key = f"{sid}#{10**13 - ts}".encode()
                leituras.put(row_key, to_bytes_map("dados", {
                    "sensor_id": sid, "valor": valor, "unidade": "C", "timestamp": ts,
                }))
                time.sleep(0.005)
            print(f"[leituras] 10 itens para {sid}")

    print("Seed concluído.")


if __name__ == "__main__":
    main()
