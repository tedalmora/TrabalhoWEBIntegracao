"""Cria as tabelas do HBase manualmente (idempotente).

Uso:

    python -m scripts.init_hbase
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Config  # noqa: E402
from app.database import TABLES, connection  # noqa: E402


def main() -> None:
    with connection() as conn:
        existentes = {t.decode() if isinstance(t, bytes) else t for t in conn.tables()}
        for short, families in TABLES.items():
            full = Config.table(short)
            if full in existentes:
                print(f"[OK] tabela {full} já existe")
                continue
            print(f"[+]  criando tabela {full} (famílias: {list(families)})")
            conn.create_table(full, families)
        print("Concluído.")


if __name__ == "__main__":
    main()
