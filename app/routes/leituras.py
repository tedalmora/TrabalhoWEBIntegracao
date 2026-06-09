"""Endpoint global de consulta de leituras (Requisito 5).

Diferentemente de ``GET /sensores/<id>/dados`` (que devolve leituras
de **um** sensor), este blueprint permite buscas mais abrangentes
combinando filtros como sensor, faixa de valores e unidade.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..config import Config
from ..database import connection
from ..utils.helpers import parse_hbase_row

bp = Blueprint("leituras", __name__, url_prefix="/leituras")


@bp.get("")
def listar_leituras():
    """Lista leituras com filtros opcionais.

    Parâmetros suportados (query string):
        - ``sensor_id``  : filtra por sensor (usa prefix scan)
        - ``valor_min``  : limite inferior numérico
        - ``valor_max``  : limite superior numérico
        - ``unidade``    : ex. ``C``, ``%``
        - ``limite``     : máximo de itens (default 100)

    Exemplo:
        ``GET /leituras?sensor_id=sen_temp_01&valor_min=20&valor_max=30``
    """
    sensor_id = request.args.get("sensor_id")
    unidade = request.args.get("unidade")
    valor_min = _to_float(request.args.get("valor_min"))
    valor_max = _to_float(request.args.get("valor_max"))
    limite = int(request.args.get("limite", "100"))

    resultados: list[dict] = []
    with connection() as conn:
        tabela = conn.table(Config.table("leituras"))
        # ``row_prefix`` deixa o HBase fazer o filtro principal;
        # os demais são aplicados em Python sobre o resultado.
        kwargs = {"limit": limite}
        if sensor_id:
            kwargs["row_prefix"] = f"{sensor_id}#".encode()

        for _, row in tabela.scan(**kwargs):
            item = parse_hbase_row(row)
            if unidade and item.get("unidade") != unidade:
                continue
            valor = _to_float(item.get("valor"))
            if valor_min is not None and (valor is None or valor < valor_min):
                continue
            if valor_max is not None and (valor is None or valor > valor_max):
                continue
            resultados.append(item)

    return jsonify({"total": len(resultados), "leituras": resultados})


def _to_float(v):
    """Converte string → float, devolvendo None em valores inválidos."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
