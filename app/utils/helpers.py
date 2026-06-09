"""Funções utilitárias compartilhadas pelas rotas.

Concentram a conversão entre dicts Python e o formato esperado pelo
HappyBase, além de geradores de id e timestamp.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Mapping


def gerar_id(prefixo: str = "") -> str:
    """Gera um identificador curto baseado em UUID4.

    Exemplo: ``gerar_id("sen_")`` → ``"sen_3f2a91b04c1d"``.
    """
    novo = uuid.uuid4().hex[:12]
    return f"{prefixo}{novo}" if prefixo else novo


def agora_ms() -> int:
    """Retorna o timestamp atual em milissegundos (UTC)."""
    return int(time.time() * 1000)


def to_bytes_map(prefix: str, data: Mapping[str, Any]) -> dict[bytes, bytes]:
    """Converte ``{coluna: valor}`` em ``{b"familia:col": b"valor"}``.

    HappyBase exige chaves e valores em bytes; esta função padroniza a
    serialização (``str(valor).encode()``) e pula valores ``None``.
    """
    out: dict[bytes, bytes] = {}
    for chave, valor in data.items():
        if valor is None:
            continue
        out[f"{prefix}:{chave}".encode()] = str(valor).encode()
    return out


def parse_hbase_row(row: Mapping[bytes, bytes]) -> dict[str, str]:
    """Converte uma linha do HBase em ``{coluna_sem_familia: valor_str}``.

    Remove o prefixo ``familia:`` para deixar o JSON de resposta mais
    enxuto. Tudo é devolvido como string — o cliente decide o tipo.
    """
    out: dict[str, str] = {}
    for raw_key, raw_val in row.items():
        key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
        val = raw_val.decode() if isinstance(raw_val, bytes) else str(raw_val)
        if ":" in key:
            key = key.split(":", 1)[1]
        out[key] = val
    return out
