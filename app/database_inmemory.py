"""Backend em memória que imita a interface do HappyBase.

Permite executar a API **sem** subir HBase nem Docker. Útil para:
    * desenvolvimento local rápido
    * testes automatizados (CI)
    * demonstração em sala sem depender de infraestrutura

A interface implementada cobre apenas o subconjunto de métodos usado
pelas rotas: ``tables``, ``create_table``, ``table``, ``close``,
``row``, ``put``, ``delete``, ``scan``. Não é uma implementação fiel
de HBase — é apenas suficiente para os endpoints deste trabalho.

Os dados ficam num dicionário global no processo; portanto:
    * Reiniciar o servidor zera o estado.
    * Não há concorrência entre workers do gunicorn — use 1 worker se
      precisar de estado consistente: ``gunicorn -w 1 ...``.
"""
from __future__ import annotations

import threading
from typing import Iterator

# Estrutura: {nome_tabela: {row_key_bytes: {col_bytes: val_bytes}}}
_STORE: dict[str, dict[bytes, dict[bytes, bytes]]] = {}
# Famílias declaradas por tabela (para validação superficial)
_FAMILIES: dict[str, dict[str, dict]] = {}
_LOCK = threading.RLock()


class _FakeTable:
    """Tabela falsa com métodos compatíveis com ``happybase.Table``."""

    def __init__(self, name: str) -> None:
        self.name = name

    # ---- leitura ----------------------------------------------------
    def row(self, key: bytes) -> dict[bytes, bytes]:
        """Retorna a linha como dict ``{b"familia:col": b"valor"}``."""
        with _LOCK:
            return dict(_STORE.get(self.name, {}).get(key, {}))

    def scan(
        self,
        row_prefix: bytes | None = None,
        limit: int | None = None,
        **_ignored,
    ) -> Iterator[tuple[bytes, dict[bytes, bytes]]]:
        """Itera por (key, row) ordenadas por row key.

        Suporta apenas os parâmetros usados pelo projeto:
        ``row_prefix`` e ``limit``.
        """
        with _LOCK:
            data = _STORE.get(self.name, {})
            # Ordena por row key para imitar o comportamento do HBase
            keys = sorted(data.keys())
            count = 0
            for k in keys:
                if row_prefix and not k.startswith(row_prefix):
                    continue
                yield k, dict(data[k])
                count += 1
                if limit is not None and count >= limit:
                    break

    # ---- escrita ----------------------------------------------------
    def put(self, key: bytes, data: dict[bytes, bytes]) -> None:
        """Insere/atualiza colunas de uma linha (merge, igual ao HBase)."""
        with _LOCK:
            tabela = _STORE.setdefault(self.name, {})
            linha = tabela.setdefault(key, {})
            linha.update(data)

    def delete(self, key: bytes, columns: list[bytes] | None = None) -> None:
        """Remove a linha inteira (ou colunas específicas, se fornecidas)."""
        with _LOCK:
            tabela = _STORE.get(self.name, {})
            if columns is None:
                tabela.pop(key, None)
            else:
                linha = tabela.get(key)
                if linha:
                    for col in columns:
                        linha.pop(col, None)


class FakeConnection:
    """Connection falsa com métodos compatíveis com ``happybase.Connection``."""

    # ---- ciclo de vida ----------------------------------------------
    def close(self) -> None:  # noqa: D401 - api compat
        """No-op (não há socket real para fechar)."""
        return None

    # ---- metadados --------------------------------------------------
    def tables(self) -> list[bytes]:
        with _LOCK:
            return [name.encode() for name in _STORE.keys()]

    def create_table(self, name: str, families: dict[str, dict]) -> None:
        """Cria tabela se ainda não existir. Falha silenciosa se já existe."""
        with _LOCK:
            _STORE.setdefault(name, {})
            _FAMILIES[name] = dict(families)

    def table(self, name: str) -> _FakeTable:
        # Cria sob demanda para evitar KeyError caso init_db não tenha rodado
        with _LOCK:
            _STORE.setdefault(name, {})
        return _FakeTable(name)


def reset() -> None:
    """Apaga todo o estado em memória — útil em testes."""
    with _LOCK:
        _STORE.clear()
        _FAMILIES.clear()
