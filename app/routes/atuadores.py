"""Endpoints para gerenciamento de **atuadores** e envio de comandos.

Atuadores diferem de sensores porque possuem um *estado* controlável
(ligado/desligado, aberto/fechado, etc.). O endpoint POST
``/atuadores/<id>/comando`` materializa o **Requisito 2** do enunciado:
envio de comando recebendo um status (sucesso/falha) como resposta.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request, abort

from ..config import Config
from ..database import connection
from ..utils.helpers import agora_ms, gerar_id, parse_hbase_row, to_bytes_map

bp = Blueprint("atuadores", __name__, url_prefix="/atuadores")

# Whitelist de comandos aceitos — facilita auditória e evita injeção
# de estados arbitrários pelo cliente.
COMANDOS_VALIDOS = {"LIGAR", "DESLIGAR", "ABRIR", "FECHAR", "RESET"}


@bp.post("")
def criar_atuador():
    body = request.get_json(silent=True) or {}
    nome = body.get("nome")
    tipo = body.get("tipo")
    if not nome or not tipo:
        abort(400, description="campos 'nome' e 'tipo' são obrigatórios")

    atuador_id = body.get("id") or gerar_id("atu_")
    info = {
        "nome": nome,
        "tipo": tipo,
        "localizacao": body.get("localizacao", ""),
        "criado_em": agora_ms(),
    }
    estado = {"atual": body.get("estado_inicial", "DESLIGADO"), "atualizado_em": agora_ms()}

    with connection() as conn:
        tabela = conn.table(Config.table("atuadores"))
        dados = {**to_bytes_map("info", info), **to_bytes_map("estado", estado)}
        tabela.put(atuador_id.encode(), dados)

    return jsonify({
        "status": "sucesso",
        "mensagem": "atuador criado",
        "id": atuador_id,
        "dados": {**info, "estado": estado["atual"]},
    }), 201


@bp.get("")
def listar_atuadores():
    tipo = request.args.get("tipo")
    estado = request.args.get("estado")
    resultados: list[dict] = []
    with connection() as conn:
        tabela = conn.table(Config.table("atuadores"))
        for key, row in tabela.scan():
            dados = parse_hbase_row(row)
            if tipo and dados.get("tipo", "").lower() != tipo.lower():
                continue
            if estado and dados.get("atual", "").lower() != estado.lower():
                continue
            resultados.append({"id": key.decode(), **dados})
    return jsonify({"total": len(resultados), "itens": resultados})


@bp.get("/<atuador_id>")
def obter_atuador(atuador_id: str):
    with connection() as conn:
        tabela = conn.table(Config.table("atuadores"))
        row = tabela.row(atuador_id.encode())
    if not row:
        abort(404, description=f"atuador {atuador_id} não encontrado")
    return jsonify({"id": atuador_id, **parse_hbase_row(row)})


@bp.post("/<atuador_id>/comando")
def enviar_comando(atuador_id: str):
    """Envia um comando para um atuador (Requisito 2).

    Corpo JSON::

        {"comando": "LIGAR"}

    Resposta tem o campo ``status`` indicando ``sucesso`` ou ``falha``
    — cobrindo o cenário pedido pelo enunciado: "operação bem sucedida,
    mal sucedida, etc.".
    """
    # 1. Sanitização básica do comando recebido.
    body = request.get_json(silent=True) or {}
    comando = (body.get("comando") or "").upper().strip()
    if not comando:
        abort(400, description="campo 'comando' é obrigatório")
    if comando not in COMANDOS_VALIDOS:
        return jsonify({
            "status": "falha",
            "mensagem": f"comando inválido: {comando}",
            "comandos_validos": sorted(COMANDOS_VALIDOS),
        }), 400

    # 2. Confirma que o atuador existe e aplica a transição de estado.
    with connection() as conn:
        tabela = conn.table(Config.table("atuadores"))
        atual = tabela.row(atuador_id.encode())
        if not atual:
            return jsonify({"status": "falha", "mensagem": f"atuador {atuador_id} não encontrado"}), 404

        novo_estado = _aplicar_comando(comando)
        # Apenas a família ``estado`` é atualizada — ``info`` fica intacta.
        tabela.put(
            atuador_id.encode(),
            to_bytes_map("estado", {"atual": novo_estado, "atualizado_em": agora_ms()}),
        )

    return jsonify({
        "status": "sucesso",
        "mensagem": f"comando {comando} executado",
        "atuador_id": atuador_id,
        "estado_atual": novo_estado,
    })


def _aplicar_comando(comando: str) -> str:
    """Máquina de estados simples: traduz comando → novo estado."""
    mapa = {
        "LIGAR": "LIGADO",
        "DESLIGAR": "DESLIGADO",
        "ABRIR": "ABERTO",
        "FECHAR": "FECHADO",
        "RESET": "DESLIGADO",
    }
    return mapa[comando]
