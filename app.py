"""API REST de gerência de sensores IoT — versão simples (arquivo único).

* Flask + HBase (via HappyBase). Se HBase indisponível, cai no modo
  em memória definindo a variável USE_INMEMORY_DB=1.
* Integração com OpenWeatherMap como webservice externo.

Endpoints (todos JSON):
  GET    /                              catálogo
  GET    /health                        status
  POST   /sensores                      cria sensor
  GET    /sensores?tipo=...             lista com filtro
  GET    /sensores/<id>                 busca por chave
  PUT    /sensores/<id>                 atualiza
  DELETE /sensores/<id>                 remove
  POST   /sensores/<id>/dados           envia leitura
  GET    /sensores/<id>/dados           leituras de um sensor
  GET    /leituras?sensor_id=...        lista global com filtros
  POST   /atuadores                     cria atuador
  GET    /atuadores                     lista atuadores
  GET    /atuadores/<id>                busca atuador
  POST   /atuadores/<id>/comando        envia comando (sucesso/falha)
  GET    /clima?cidade=Curitiba,BR      webservice externo
"""
import os
import time
import uuid
import threading
from contextlib import contextmanager

import requests
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env (quando existir).
load_dotenv()

# ---------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------
HBASE_HOST = os.getenv("HBASE_HOST", "localhost")
HBASE_PORT = int(os.getenv("HBASE_PORT", "9090"))
TABLE_PREFIX = os.getenv("HBASE_TABLE_PREFIX", "iot")
# Quando true, ignora HBase real e usa armazenamento em memória.
USE_INMEMORY = os.getenv("USE_INMEMORY_DB", "0").lower() in {"1", "true", "yes", "on"}
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# Nomes físicos das tabelas no banco (com prefixo para evitar colisões).
T_SENSORES  = f"{TABLE_PREFIX}_sensores"
T_ATUADORES = f"{TABLE_PREFIX}_atuadores"
T_LEITURAS  = f"{TABLE_PREFIX}_leituras"

# Mapeia comando recebido -> estado final do atuador.
COMANDOS = {"LIGAR": "LIGADO", "DESLIGAR": "DESLIGADO",
            "ABRIR": "ABERTO", "FECHAR": "FECHADO", "RESET": "DESLIGADO"}


# ---------------------------------------------------------------------
# Camada de dados: HBase real ou backend em memória (fallback)
# ---------------------------------------------------------------------
try:
    import happybase  # type: ignore
except Exception:
    # Se a lib não existir, ainda podemos rodar no modo em memória.
    happybase = None

# Backend em memória: dict + lock. Usado quando USE_INMEMORY_DB=1.
_MEM: dict[str, dict[bytes, dict[bytes, bytes]]] = {}
_MEM_LOCK = threading.RLock()


class _MemTable:
    """Tabela fake com a mesma interface básica usada no HappyBase."""
    def __init__(self, name): self.name = name
    def row(self, key):
        # Retorna cópia para não vazar referência mutável interna.
        with _MEM_LOCK:
            return dict(_MEM.get(self.name, {}).get(key, {}))
    def put(self, key, data):
        # Upsert de colunas (comportamento equivalente ao HBase put).
        with _MEM_LOCK:
            _MEM.setdefault(self.name, {}).setdefault(key, {}).update(data)
    def delete(self, key):
        with _MEM_LOCK:
            _MEM.get(self.name, {}).pop(key, None)
    def scan(self, row_prefix=None, limit=None, **_):
        # Ordena chaves para simular scan lexicográfico do HBase.
        with _MEM_LOCK:
            keys = sorted(_MEM.get(self.name, {}).keys())
        for i, k in enumerate(keys):
            if row_prefix and not k.startswith(row_prefix):
                continue
            if limit is not None and i >= limit:
                break
            yield k, self.row(k)


class _MemConnection:
    """Conexão fake (somente métodos usados pela API)."""
    def tables(self):
        with _MEM_LOCK:
            return [n.encode() for n in _MEM]
    def create_table(self, name, _families):
        with _MEM_LOCK:
            _MEM.setdefault(name, {})
    def table(self, name):
        with _MEM_LOCK:
            _MEM.setdefault(name, {})
        return _MemTable(name)
    def close(self): pass


@contextmanager
def conexao():
    """Abre conexão com HBase ou devolve a fake em memória."""
    # Se USE_INMEMORY_DB estiver ativo (ou happybase indisponível),
    # usamos implementação local sem dependência externa.
    if USE_INMEMORY or happybase is None:
        conn = _MemConnection()
    else:
        # HappyBase usa Thrift por trás para conversar com o HBase.
        conn = happybase.Connection(host=HBASE_HOST, port=HBASE_PORT)
    try:
        yield conn
    finally:
        try: conn.close()
        except Exception: pass


def init_tabelas():
    """Cria as 3 tabelas se ainda não existirem (idempotente)."""
    # "famílias" são o agrupamento de colunas no modelo colunar do HBase.
    schema = {T_SENSORES: {"info": {}},
              T_ATUADORES: {"info": {}, "estado": {}},
              T_LEITURAS: {"dados": {}}}
    with conexao() as conn:
        existentes = {t.decode() if isinstance(t, bytes) else t for t in conn.tables()}
        for nome, fam in schema.items():
            if nome not in existentes:
                conn.create_table(nome, fam)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def gerar_id(prefixo):
    """Gera id curto com prefixo (ex.: sen_abc123...)."""
    return f"{prefixo}{uuid.uuid4().hex[:12]}"


def agora_ms():
    """Timestamp atual em milissegundos."""
    return int(time.time() * 1000)

def to_hbase(familia, dados):
    """Converte {col: valor} -> {b'familia:col': b'valor'}, ignorando None."""
    return {f"{familia}:{k}".encode(): str(v).encode()
            for k, v in dados.items() if v is not None}

def from_hbase(row):
    """Converte uma linha HBase em dict simples (sem 'familia:')."""
    out = {}
    for k, v in row.items():
        chave = k.decode() if isinstance(k, bytes) else k
        if ":" in chave:
            chave = chave.split(":", 1)[1]
        out[chave] = v.decode() if isinstance(v, bytes) else v
    return out


# ---------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------
app = Flask(__name__)
# Permite chamadas de front-end em outra origem (localhost:3000 etc.).
CORS(app)

try:
    init_tabelas()
except Exception as exc:
    # O app sobe mesmo sem banco para permitir diagnóstico via /health.
    app.logger.warning("Banco indisponível no startup: %s", exc)


@app.get("/")
def index():
    """Endpoint de descoberta: lista os recursos disponíveis na API."""
    return jsonify({
        "servico": "API de Gerência de Sensores IoT",
        "endpoints": [
            "GET    /health",
            "POST   /sensores",
            "GET    /sensores?tipo=&localizacao=",
            "GET    /sensores/<id>",
            "PUT    /sensores/<id>",
            "DELETE /sensores/<id>",
            "POST   /sensores/<id>/dados",
            "GET    /sensores/<id>/dados",
            "GET    /leituras?sensor_id=&valor_min=&valor_max=",
            "POST   /atuadores",
            "GET    /atuadores",
            "GET    /atuadores/<id>",
            "POST   /atuadores/<id>/comando",
            "GET    /clima?cidade=Curitiba,BR",
        ],
    })


@app.get("/health")
def health():
    """Health check da aplicação e da conectividade com o backend."""
    try:
        with conexao() as conn:
            conn.tables()
        return jsonify({"api": "ok", "banco": "ok"})
    except Exception as exc:
        return jsonify({"api": "ok", "banco": f"erro: {exc}"}), 503


# ---- SENSORES --------------------------------------------------------
@app.post("/sensores")
def criar_sensor():
    """Cadastra um novo sensor."""
    # Tenta ler JSON; se vier inválido, usamos dict vazio para validar depois.
    body = request.get_json(silent=True) or {}
    if not body.get("tipo") or not body.get("localizacao"):
        abort(400, description="Campos 'tipo' e 'localizacao' são obrigatórios")

    # Se o cliente não enviar id, a API gera automaticamente.
    sid = body.get("id") or gerar_id("sen_")
    registro = {
        "tipo": body["tipo"],
        "localizacao": body["localizacao"],
        "descricao": body.get("descricao", ""),
        "criado_em": agora_ms(),
    }
    with conexao() as conn:
        # Persistência no HBase: rowkey = sid, colunas em família "info".
        conn.table(T_SENSORES).put(sid.encode(), to_hbase("info", registro))
    return jsonify({"status": "sucesso", "id": sid, "dados": registro}), 201


@app.get("/sensores/<sid>")
def obter_sensor(sid):
    """Busca sensor por chave primária (rowkey)."""
    with conexao() as conn:
        row = conn.table(T_SENSORES).row(sid.encode())
    if not row:
        abort(404, description=f"sensor {sid} não encontrado")
    return jsonify({"id": sid, **from_hbase(row)})


@app.get("/sensores")
def listar_sensores():
    """Lista sensores com filtros opcionais tipo/localização."""
    tipo = request.args.get("tipo")
    local = request.args.get("localizacao")
    out = []
    with conexao() as conn:
        for key, row in conn.table(T_SENSORES).scan():
            d = from_hbase(row)
            # Filtros em memória após scan da tabela.
            if tipo and d.get("tipo", "").lower() != tipo.lower(): continue
            if local and local.lower() not in d.get("localizacao", "").lower(): continue
            out.append({"id": key.decode(), **d})
    return jsonify({"total": len(out), "itens": out})


@app.put("/sensores/<sid>")
def atualizar_sensor(sid):
    """Atualiza apenas os campos permitidos de um sensor existente."""
    body = request.get_json(silent=True) or {}
    if not body: abort(400, description="corpo vazio")
    permitidos = {k: body[k] for k in ("tipo", "localizacao", "descricao") if k in body}
    if not permitidos: abort(400, description="nenhum campo válido para atualizar")
    with conexao() as conn:
        tabela = conn.table(T_SENSORES)
        if not tabela.row(sid.encode()):
            abort(404, description=f"sensor {sid} não encontrado")
        tabela.put(sid.encode(), to_hbase("info", permitidos))
    return jsonify({"status": "sucesso", "id": sid})


@app.delete("/sensores/<sid>")
def remover_sensor(sid):
    """Remove o cadastro do sensor."""
    with conexao() as conn:
        tabela = conn.table(T_SENSORES)
        if not tabela.row(sid.encode()):
            abort(404, description=f"sensor {sid} não encontrado")
        tabela.delete(sid.encode())
    return jsonify({"status": "sucesso", "id": sid})


@app.post("/sensores/<sid>/dados")
def enviar_leitura(sid):
    """Recebe leitura de sensor e grava no histórico."""
    body = request.get_json(silent=True) or {}
    if body.get("valor") is None:
        abort(400, description="campo 'valor' é obrigatório")
    with conexao() as conn:
        if not conn.table(T_SENSORES).row(sid.encode()):
            abort(404, description=f"sensor {sid} não cadastrado")
        ts = agora_ms()
        # row key com timestamp invertido: as leituras mais recentes
        # vêm primeiro num scan por prefixo (truque clássico do HBase).
        row_key = f"{sid}#{10**13 - ts}".encode()
        leitura = {"sensor_id": sid, "valor": body["valor"],
                   "unidade": body.get("unidade", ""), "timestamp": ts}
        conn.table(T_LEITURAS).put(row_key, to_hbase("dados", leitura))
    return jsonify({"status": "sucesso", "sensor_id": sid,
                    "valor": body["valor"], "timestamp": ts}), 201


@app.get("/sensores/<sid>/dados")
def listar_leituras_sensor(sid):
    """Lista leituras de um sensor específico (mais recentes primeiro)."""
    limite = int(request.args.get("limite", "50"))
    out = []
    with conexao() as conn:
        for _, row in conn.table(T_LEITURAS).scan(row_prefix=f"{sid}#".encode(), limit=limite):
            out.append(from_hbase(row))
    return jsonify({"sensor_id": sid, "total": len(out), "leituras": out})


# ---- LEITURAS (consulta global com filtros) --------------------------
def _to_float(v):
    """Converte query string para float com fallback seguro."""
    try: return float(v) if v not in (None, "") else None
    except (TypeError, ValueError): return None


@app.get("/leituras")
def listar_leituras():
    """Consulta global de leituras com múltiplos filtros opcionais."""
    sensor_id = request.args.get("sensor_id")
    vmin = _to_float(request.args.get("valor_min"))
    vmax = _to_float(request.args.get("valor_max"))
    unidade = request.args.get("unidade")
    limite = int(request.args.get("limite", "100"))
    out = []
    with conexao() as conn:
        kwargs = {"limit": limite}
        # Prefix-scan reduz custo quando o filtro por sensor está presente.
        if sensor_id: kwargs["row_prefix"] = f"{sensor_id}#".encode()
        for _, row in conn.table(T_LEITURAS).scan(**kwargs):
            item = from_hbase(row)
            if unidade and item.get("unidade") != unidade: continue
            v = _to_float(item.get("valor"))
            if vmin is not None and (v is None or v < vmin): continue
            if vmax is not None and (v is None or v > vmax): continue
            out.append(item)
    return jsonify({"total": len(out), "leituras": out})


# ---- ATUADORES -------------------------------------------------------
@app.post("/atuadores")
def criar_atuador():
    """Cadastra atuador com informações básicas e estado inicial."""
    body = request.get_json(silent=True) or {}
    if not body.get("nome") or not body.get("tipo"):
        abort(400, description="campos 'nome' e 'tipo' são obrigatórios")
    aid = body.get("id") or gerar_id("atu_")
    info = {"nome": body["nome"], "tipo": body["tipo"],
            "localizacao": body.get("localizacao", ""), "criado_em": agora_ms()}
    estado = {"atual": body.get("estado_inicial", "DESLIGADO"), "atualizado_em": agora_ms()}
    with conexao() as conn:
        # Escreve info e estado na mesma row do atuador.
        conn.table(T_ATUADORES).put(aid.encode(),
                                    {**to_hbase("info", info), **to_hbase("estado", estado)})
    return jsonify({"status": "sucesso", "id": aid,
                    "dados": {**info, "estado": estado["atual"]}}), 201


@app.get("/atuadores")
def listar_atuadores():
    """Lista atuadores filtrando por tipo e/ou estado."""
    tipo = request.args.get("tipo")
    estado = request.args.get("estado")
    out = []
    with conexao() as conn:
        for key, row in conn.table(T_ATUADORES).scan():
            d = from_hbase(row)
            if tipo and d.get("tipo", "").lower() != tipo.lower(): continue
            if estado and d.get("atual", "").lower() != estado.lower(): continue
            out.append({"id": key.decode(), **d})
    return jsonify({"total": len(out), "itens": out})


@app.get("/atuadores/<aid>")
def obter_atuador(aid):
    """Busca atuador por id."""
    with conexao() as conn:
        row = conn.table(T_ATUADORES).row(aid.encode())
    if not row:
        abort(404, description=f"atuador {aid} não encontrado")
    return jsonify({"id": aid, **from_hbase(row)})


@app.post("/atuadores/<aid>/comando")
def enviar_comando(aid):
    """Aplica comando no atuador e devolve status da operação."""
    body = request.get_json(silent=True) or {}
    comando = (body.get("comando") or "").upper().strip()
    if not comando:
        abort(400, description="campo 'comando' é obrigatório")
    if comando not in COMANDOS:
        # Falha de validação: comando fora da whitelist.
        return jsonify({"status": "falha", "mensagem": f"comando inválido: {comando}",
                        "comandos_validos": sorted(COMANDOS)}), 400
    with conexao() as conn:
        tabela = conn.table(T_ATUADORES)
        if not tabela.row(aid.encode()):
            return jsonify({"status": "falha", "mensagem": f"atuador {aid} não encontrado"}), 404
        # Calcula novo estado e persiste na família "estado".
        novo = COMANDOS[comando]
        tabela.put(aid.encode(), to_hbase("estado", {"atual": novo, "atualizado_em": agora_ms()}))
    return jsonify({"status": "sucesso", "atuador_id": aid,
                    "comando": comando, "estado_atual": novo})


# ---- WEBSERVICE EXTERNO ---------------------------------------------
@app.get("/clima")
def consultar_clima():
    """Consulta clima atual na OpenWeatherMap e devolve payload simplificado."""
    if not OPENWEATHER_API_KEY:
        return jsonify({"status": "falha", "mensagem": "OPENWEATHER_API_KEY não configurada"}), 502
    cidade = request.args.get("cidade", "Curitiba,BR")
    try:
        # timeout evita requisição "pendurada" em rede instável.
        r = requests.get("https://api.openweathermap.org/data/2.5/weather",
                         params={"q": cidade, "appid": OPENWEATHER_API_KEY,
                                 "units": "metric", "lang": "pt_br"}, timeout=10)
    except requests.RequestException as exc:
        return jsonify({"status": "falha", "mensagem": str(exc)}), 502
    if r.status_code != 200:
        return jsonify({"status": "falha", "mensagem": r.text}), 502
    d = r.json()
    return jsonify({
        "status": "sucesso", "fonte": "OpenWeatherMap",
        "dados": {
            "cidade": d.get("name"),
            "pais": (d.get("sys") or {}).get("country"),
            "temperatura": (d.get("main") or {}).get("temp"),
            "umidade": (d.get("main") or {}).get("humidity"),
            "descricao": ((d.get("weather") or [{}])[0]).get("description"),
        },
    })


# ---- Erros em JSON ---------------------------------------------------
@app.errorhandler(400)
def _e400(e): return jsonify({"erro": str(e.description)}), 400

@app.errorhandler(404)
def _e404(_): return jsonify({"erro": "recurso não encontrado"}), 404

@app.errorhandler(500)
def _e500(_): return jsonify({"erro": "erro interno do servidor"}), 500


# ---------------------------------------------------------------------
if __name__ == "__main__":
    # debug=True facilita desenvolvimento local (auto-reload + traceback).
    # Em produção, execute com servidor WSGI e debug desabilitado.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
