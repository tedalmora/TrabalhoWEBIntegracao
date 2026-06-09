"""Camada de acesso ao banco de dados.

Por padrão usa **Apache HBase** via HappyBase (Thrift). Se a variável
de ambiente ``USE_INMEMORY_DB=1`` estiver definida, usa um backend
fake em memória implementado em :mod:`app.database_inmemory` —
útil para rodar a API e os testes sem subir Docker/HBase.

Estrutura das tabelas (todas com prefixo configurável, por padrão ``iot_``):

* ``iot_sensores``  → família ``info``   (tipo, localizacao, descricao, criado_em)
* ``iot_atuadores`` → famílias ``info`` (nome, tipo, localizacao) e ``estado`` (atual, atualizado_em)
* ``iot_leituras``  → família ``dados``  (sensor_id, valor, unidade, timestamp)
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from flask import Flask

from .config import Config
from .database_inmemory import FakeConnection

# happybase é opcional — só é necessário no modo HBase real. Se a biblioteca
# não estiver instalada (ou der import error, como acontece com versões antigas
# em Python 3.14 por causa do removido pkg_resources), o modo in-memory ainda
# funciona normalmente.
try:
    import happybase  # type: ignore
except Exception:  # noqa: BLE001 - happybase pode falhar com ImportError ou ModuleNotFoundError
    happybase = None  # type: ignore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Schema declarado de forma estática. Lido por init_db e pelos scripts.
# ---------------------------------------------------------------------
TABLES: dict[str, dict[str, dict]] = {
    "sensores":  {"info":  {}},
    "atuadores": {"info":  {}, "estado": {}},
    "leituras":  {"dados": {}},
}


def _use_inmemory() -> bool:
    """Retorna ``True`` se o backend em memória deve ser usado."""
    return os.getenv("USE_INMEMORY_DB", "0").lower() in {"1", "true", "yes", "on"}


def get_connection():
    """Cria uma nova conexão com o backend escolhido.

    * Modo fake:  retorna :class:`FakeConnection` (sem rede).
    * Modo real:  abre conexão Thrift com o HBase.
    """
    if _use_inmemory():
        return FakeConnection()
    if happybase is None:
        raise RuntimeError(
            "happybase não está instalado. Defina USE_INMEMORY_DB=1 "
            "para usar o backend em memória, ou instale happybase."
        )
    return happybase.Connection(
        host=Config.HBASE_HOST,
        port=Config.HBASE_PORT,
        autoconnect=True,
    )


@contextmanager
def connection() -> Iterator:
    """Context manager que garante o ``close()`` da conexão.

    Uso::

        with connection() as conn:
            tabela = conn.table(Config.table("sensores"))
            ...
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 - não mascarar erros de negócio
            pass


def init_db(app: Flask) -> None:
    """Cria as tabelas no backend caso ainda não existam (idempotente).

    Executado no startup pelo :func:`app.create_app`. Se o HBase
    estiver indisponível e o modo fake não estiver ativo, o erro é
    apenas logado — o operador pode então definir
    ``USE_INMEMORY_DB=1`` e reiniciar para continuar trabalhando.
    """
    with connection() as conn:
        existing = {t.decode() if isinstance(t, bytes) else t for t in conn.tables()}
        for short_name, families in TABLES.items():
            full = Config.table(short_name)
            if full not in existing:
                app.logger.info("Criando tabela %s", full)
                conn.create_table(full, families)
            else:
                app.logger.debug("Tabela %s já existe", full)
