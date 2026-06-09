"""Endpoints relacionados a **sensores** e suas leituras.

Este blueprint cobre o ciclo de vida completo de um sensor IoT:
cadastro, busca, atualização, remoção, ingestão de leituras e
consulta histórica de leituras por sensor.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request, abort

from ..config import Config
from ..database import connection
from ..utils.helpers import agora_ms, gerar_id, parse_hbase_row, to_bytes_map

# Todos os endpoints deste módulo ficam sob o prefixo /sensores.
bp = Blueprint("sensores", __name__, url_prefix="/sensores")


@bp.post("")
def criar_sensor():
    """Registra um novo sensor (atende ao endpoint POST /sensores).

    Corpo JSON esperado::

        {
          "tipo": "temperatura",
          "localizacao": "Sala 101",
          "descricao": "Sensor DHT22"
        }

    O ``id`` é opcional — se omitido, é gerado automaticamente.
    """
    # 1. Validação mínima do payload.
    body = request.get_json(silent=True) or {}
    tipo = body.get("tipo")
    localizacao = body.get("localizacao")
    if not tipo or not localizacao:
        abort(400, description="Campos 'tipo' e 'localizacao' são obrigatórios")

    # 2. Monta o registro e grava na tabela ``iot_sensores`` (família ``info``).
    sensor_id = body.get("id") or gerar_id("sen_")
    registro = {
        "tipo": tipo,
        "localizacao": localizacao,
        "descricao": body.get("descricao", ""),
        "criado_em": agora_ms(),
    }
    with connection() as conn:
        tabela = conn.table(Config.table("sensores"))
        tabela.put(sensor_id.encode(), to_bytes_map("info", registro))

    return jsonify({
        "status": "sucesso",
        "mensagem": "sensor criado",
        "id": sensor_id,
        "dados": registro,
    }), 201


@bp.get("/<sensor_id>")
def obter_sensor(sensor_id: str):
    """Busca um sensor pela chave identificadora (Requisito 3).

    Faz lookup direto pela rowkey — operação O(1) no HBase.
    """
    with connection() as conn:
        tabela = conn.table(Config.table("sensores"))
        row = tabela.row(sensor_id.encode())
    if not row:
        abort(404, description=f"sensor {sensor_id} não encontrado")
    return jsonify({"id": sensor_id, **parse_hbase_row(row)})


@bp.get("")
def listar_sensores():
    """Lista sensores com filtros opcionais (Requisito 5).

    Parâmetros de query suportados:
        * ``tipo``        — comparação exata, case-insensitive
        * ``localizacao`` — substring, case-insensitive

    Exemplos:
        * ``GET /sensores``
        * ``GET /sensores?tipo=temperatura``
        * ``GET /sensores?localizacao=Sala 101``
    """
    tipo = request.args.get("tipo")
    local = request.args.get("localizacao")

    # Faz scan completo e aplica os filtros em Python.
    # Para volumes muito grandes, poderia ser substituído por
    # ``scan`` com filtros server-side do HBase (FilterBase).
    resultados: list[dict] = []
    with connection() as conn:
        tabela = conn.table(Config.table("sensores"))
        for key, row in tabela.scan():
            dados = parse_hbase_row(row)
            if tipo and dados.get("tipo", "").lower() != tipo.lower():
                continue
            if local and local.lower() not in dados.get("localizacao", "").lower():
                continue
            resultados.append({"id": key.decode(), **dados})

    return jsonify({"total": len(resultados), "itens": resultados})


@bp.put("/<sensor_id>")
def atualizar_sensor(sensor_id: str):
    body = request.get_json(silent=True) or {}
    if not body:
        abort(400, description="corpo vazio")

    with connection() as conn:
        tabela = conn.table(Config.table("sensores"))
        atual = tabela.row(sensor_id.encode())
        if not atual:
            abort(404, description=f"sensor {sensor_id} não encontrado")
        permitidos = {k: body[k] for k in ("tipo", "localizacao", "descricao") if k in body}
        if not permitidos:
            abort(400, description="nenhum campo válido para atualizar")
        tabela.put(sensor_id.encode(), to_bytes_map("info", permitidos))

    return jsonify({"status": "sucesso", "mensagem": "sensor atualizado", "id": sensor_id})


@bp.delete("/<sensor_id>")
def remover_sensor(sensor_id: str):
    with connection() as conn:
        tabela = conn.table(Config.table("sensores"))
        atual = tabela.row(sensor_id.encode())
        if not atual:
            abort(404, description=f"sensor {sensor_id} não encontrado")
        tabela.delete(sensor_id.encode())
    return jsonify({"status": "sucesso", "mensagem": "sensor removido", "id": sensor_id})


@bp.post("/<sensor_id>/dados")
def enviar_leitura(sensor_id: str):
    """Recebe uma leitura enviada por um sensor (envio + status).

    Corpo JSON::

        {"valor": 23.5, "unidade": "C"}

    Falha com 404 se o sensor não existir; 400 se faltar ``valor``.
    """
    body = request.get_json(silent=True) or {}
    valor = body.get("valor")
    if valor is None:
        abort(400, description="campo 'valor' é obrigatório")

    with connection() as conn:
        # Verifica que o sensor existe antes de gravar a leitura.
        sensores = conn.table(Config.table("sensores"))
        if not sensores.row(sensor_id.encode()):
            abort(404, description=f"sensor {sensor_id} não cadastrado")

        ts = agora_ms()
        leitura = {
            "sensor_id": sensor_id,
            "valor": valor,
            "unidade": body.get("unidade", ""),
            "timestamp": ts,
        }
        # Truque de design HBase: timestamp invertido na rowkey faz com que
        # um scan por prefixo devolva primeiro as leituras mais recentes,
        # sem precisar carregar tudo na memória e ordenar.
        row_key = f"{sensor_id}#{10**13 - ts}".encode()
        leituras = conn.table(Config.table("leituras"))
        leituras.put(row_key, to_bytes_map("dados", leitura))

    return jsonify({
        "status": "sucesso",
        "mensagem": "leitura registrada",
        "sensor_id": sensor_id,
        "timestamp": ts,
        "valor": valor,
    }), 201


@bp.get("/<sensor_id>/dados")
def listar_leituras_sensor(sensor_id: str):
    """Retorna as leituras de um sensor (mais recentes primeiro).

    Usa o ``row_prefix`` do HBase, que é uma operação muito eficiente
    porque o storage é lexicograficamente ordenado por rowkey.
    """
    limite = int(request.args.get("limite", "50"))
    resultados: list[dict] = []
    with connection() as conn:
        leituras = conn.table(Config.table("leituras"))
        prefix = f"{sensor_id}#".encode()
        for _, row in leituras.scan(row_prefix=prefix, limit=limite):
            resultados.append(parse_hbase_row(row))
    return jsonify({"sensor_id": sensor_id, "total": len(resultados), "leituras": resultados})
