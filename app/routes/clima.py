"""Endpoints de integração com webservices externos (Requisito 4).

* ``GET  /clima``                       — consulta clima na OpenWeatherMap.
* ``POST /clima/sincronizar/<sensor>``  — busca o clima e registra como
  leitura do sensor informado, opcionalmente espelhando a leitura para
  o canal ThingSpeak configurado.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request, abort

from ..config import Config
from ..database import connection
from ..services.openweather_service import obter_clima
from ..services.thingspeak_service import enviar_leitura_thingspeak
from ..utils.helpers import agora_ms, parse_hbase_row, to_bytes_map

bp = Blueprint("clima", __name__)


@bp.get("/clima")
def consultar_clima():
    """Consulta clima na OpenWeatherMap.

    Exemplo: ``GET /clima?cidade=Curitiba,BR``
    """
    cidade = request.args.get("cidade", Config.OPENWEATHER_DEFAULT_CITY)
    try:
        dados = obter_clima(cidade)
    except RuntimeError as exc:
        return jsonify({"status": "falha", "mensagem": str(exc)}), 502
    return jsonify({"status": "sucesso", "fonte": "OpenWeatherMap", "dados": dados})


@bp.post("/clima/sincronizar/<sensor_id>")
def sincronizar_clima_como_leitura(sensor_id: str):
    """Busca o clima atual e registra como leitura do sensor informado.

    Demonstra dois conceitos:
      1. **Enriquecimento** de leituras com dados de fonte externa
         (OpenWeatherMap), o que valida o Requisito 4.
      2. **Integração reversa**: se ``THINGSPEAK_WRITE_KEY`` estiver
         configurada, espelha a leitura para um canal ThingSpeak,
         simulando o envio para uma plataforma IoT real.
    """
    cidade = request.args.get("cidade", Config.OPENWEATHER_DEFAULT_CITY)
    try:
        clima = obter_clima(cidade)
    except RuntimeError as exc:
        # 502: dependência externa falhou.
        return jsonify({"status": "falha", "mensagem": str(exc)}), 502

    temperatura = clima["temperatura"]
    ts = agora_ms()
    leitura = {
        "sensor_id": sensor_id,
        "valor": temperatura,
        "unidade": "C",
        "timestamp": ts,
        "origem": "openweathermap",
        "cidade": cidade,
    }

    # Grava no HBase com a mesma conven\u00e7\u00e3o de rowkey usada pelas leituras locais.
    with connection() as conn:
        sensores = conn.table(Config.table("sensores"))
        if not sensores.row(sensor_id.encode()):
            abort(404, description=f"sensor {sensor_id} não cadastrado")
        leituras = conn.table(Config.table("leituras"))
        row_key = f"{sensor_id}#{10**13 - ts}".encode()
        leituras.put(row_key, to_bytes_map("dados", leitura))

    # Envio opcional ao ThingSpeak \u2014 falhas n\u00e3o invalidam o request principal.
    thingspeak_resp = None
    if Config.THINGSPEAK_WRITE_KEY:
        try:
            thingspeak_resp = enviar_leitura_thingspeak({"field1": temperatura, "field2": clima.get("umidade")})
        except RuntimeError as exc:
            thingspeak_resp = {"erro": str(exc)}

    return jsonify({
        "status": "sucesso",
        "mensagem": "leitura sincronizada a partir do OpenWeatherMap",
        "leitura": leitura,
        "thingspeak": thingspeak_resp,
    })
