# Explicação detalhada do código

Este documento descreve **cada arquivo do projeto** e como eles se
encaixam. Use-o como roteiro de leitura quando for estudar o código.

## Visão geral em uma frase

> A aplicação é uma API REST em Flask que recebe e devolve JSON sobre
> HTTP, persistindo os dados em Apache HBase (ou em um backend
> equivalente em memória, para testes), e enriquece as leituras com
> dados meteorológicos vindos do webservice externo OpenWeatherMap.

## Mapa de pacotes

```
TrabalhoWEBIntegracao/
├── run.py                       ← bootstrap (cria a app e abre o servidor)
├── app/
│   ├── __init__.py              ← factory + registro de blueprints
│   ├── config.py                ← variáveis de ambiente
│   ├── database.py              ← escolha de backend + init_db
│   ├── database_inmemory.py     ← backend fake para rodar sem HBase
│   ├── routes/
│   │   ├── sensores.py          ← /sensores
│   │   ├── atuadores.py         ← /atuadores  (comandos)
│   │   ├── leituras.py          ← /leituras   (consultas filtradas)
│   │   └── clima.py             ← /clima      (webservice externo)
│   ├── services/
│   │   ├── openweather_service.py
│   │   └── thingspeak_service.py
│   └── utils/helpers.py         ← uuid, timestamp e conversão HBase
├── scripts/                     ← init de tabelas, seed e smoke test
└── tests/test_api.py            ← testes pytest (in-memory)
```

---

## 1. `run.py` — ponto de entrada

Lê a porta do ambiente (`PORT`), invoca a *application factory*
(`create_app`) e sobe o servidor de desenvolvimento do Flask. Em
produção, o `gunicorn` chama diretamente `run:app` — o `if __name__
== "__main__"` só é executado quando você roda `python run.py`.

## 2. `app/__init__.py` — application factory

A função `create_app()`:

1. Chama `load_dotenv()` para puxar o `.env`.
2. Cria a instância do Flask e aplica a `Config`.
3. Habilita CORS (necessário para consumo a partir de páginas web/Postman remoto).
4. Chama `init_db(app)` — cria as tabelas se ainda não existirem.
   - Encapsulado em `try/except` para o serviço subir mesmo com banco
     fora do ar; o `/health` denuncia o problema.
5. Registra os quatro **blueprints** (sensores, atuadores, leituras, clima).
6. Define `GET /` (catálogo de endpoints) e `GET /health` (status).
7. Registra `errorhandlers` para 400/404/500, garantindo que **toda**
   resposta de erro seja JSON.

O padrão *factory* permite múltiplas instâncias (produção, testes,
scripts) sem efeitos colaterais no `import`.

## 3. `app/config.py` — configuração

Classe `Config` com atributos lidos de variáveis de ambiente — única
fonte de verdade. O método de classe `Config.table("sensores")`
devolve `"iot_sensores"` (prefixo configurável), evitando colisão de
nomes em ambientes compartilhados.

## 4. `app/database.py` — abstração do banco

Responsabilidades:

- **Decidir qual backend usar.** Se `USE_INMEMORY_DB=1`, retorna uma
  `FakeConnection`; caso contrário, abre uma conexão Thrift real com
  o HBase via HappyBase.
- **`connection()`** — context manager que garante o `close()`.
- **`init_db(app)`** — cria as três tabelas (`sensores`, `atuadores`,
  `leituras`) com suas famílias de colunas se ainda não existirem.
  Idempotente: rodar de novo não dá erro.
- **`TABLES`** — dicionário declarativo com o schema; também é
  consumido pelo script `init_hbase.py`.

## 5. `app/database_inmemory.py` — backend de teste

Implementação **mínima** da interface HappyBase usando dicionários em
processo. Métodos implementados:

| Connection           | Table                          |
|----------------------|--------------------------------|
| `tables()`           | `row(key)`                     |
| `create_table(...)`  | `put(key, dict)` (merge)       |
| `table(name)`        | `delete(key, columns=None)`    |
| `close()` (no-op)    | `scan(row_prefix, limit)`      |

O `scan` mantém a **ordem lexicográfica das row keys**, replicando o
comportamento do HBase real — é graças a isso que a convenção de
row key com *timestamp invertido* funciona em ambos os modos. Há um
`reset()` usado pelos testes para limpar o estado entre casos.

## 6. `app/utils/helpers.py`

Três funções pequenas, mas centrais:

- **`gerar_id(prefixo)`** → identificador curto (`sen_3f2a91…`).
- **`agora_ms()`** → timestamp em milissegundos.
- **`to_bytes_map(prefix, data)`** → converte `{"valor": 23.4}` em
  `{b"dados:valor": b"23.4"}` (formato exigido pelo HappyBase).
- **`parse_hbase_row(row)`** → inverso: tira o prefixo da família e
  decodifica de bytes para string, deixando o JSON de resposta enxuto.

## 7. Blueprints (`app/routes/*.py`)

Cada arquivo define um `Blueprint` Flask. **Anatomia de uma rota:**

```python
@bp.post("/<sensor_id>/dados")
def enviar_leitura(sensor_id):
    body = request.get_json(...)          # 1. parse do corpo
    if not body.get("valor"):             # 2. validação
        abort(400, ...)
    with connection() as conn:            # 3. abre conexão
        tabela = conn.table(Config.table("leituras"))
        tabela.put(row_key, to_bytes_map("dados", leitura))  # 4. grava
    return jsonify({"status": "sucesso", ...}), 201          # 5. responde
```

### 7.1 `sensores.py`
CRUD completo de sensores + ingestão e consulta de leituras de um
sensor. Destaques:
- `POST /sensores/<id>/dados` usa **row key invertida**
  (`{sensor}#{10^13 - ts}`) para que `scan(row_prefix=)` traga as
  leituras mais novas primeiro — sem precisar carregar tudo na
  memória nem ordenar.
- `GET /sensores?tipo=…&localizacao=…` faz scan e aplica filtros em
  Python; para volumes muito grandes seria substituível por filtros
  server-side do HBase.

### 7.2 `atuadores.py`
Cobre o **Requisito 2** (envio + status). Diferenças em relação a
sensores:
- Há duas famílias de colunas: `info` (estático) e `estado` (mutável).
- O endpoint `POST /atuadores/<id>/comando` valida o comando contra
  uma **whitelist** `COMANDOS_VALIDOS` e devolve `status: sucesso` ou
  `status: falha` com a razão.
- A função privada `_aplicar_comando` é a *máquina de estados*
  (`LIGAR → LIGADO`, etc.).

### 7.3 `leituras.py`
**Requisito 5**. Endpoint único `GET /leituras` que combina
`sensor_id`, `valor_min`, `valor_max`, `unidade` e `limite`.
Quando há `sensor_id`, o filtro vira *prefix scan* (eficiente);
os demais filtros são aplicados em Python sobre a sequência
devolvida.

### 7.4 `clima.py`
**Requisito 4**. Dois endpoints:

| Endpoint                              | O que faz |
|---------------------------------------|-----------|
| `GET /clima?cidade=...`               | proxy simples sobre OpenWeatherMap, com dict normalizado |
| `POST /clima/sincronizar/<sensor>`    | busca o clima, grava como leitura do sensor, espelha no ThingSpeak (se chave estiver configurada) |

Erros do serviço externo viram **HTTP 502** para deixar claro que o
problema não é local.

## 8. Services (`app/services/*.py`)

Camada *thin* entre a rota e o webservice externo. Cada service:

- Falha cedo se a credencial não estiver configurada.
- Encapsula `requests` em `try/except` para mapear erros de rede em
  `RuntimeError` (que vira HTTP 502 na rota).
- **Normaliza** o payload de resposta — a rota não conhece o JSON cru
  da API externa.

## 9. Scripts (`scripts/*.py`)

- **`init_hbase.py`** — cria as tabelas manualmente. Útil em pipelines
  de deploy ou quando você sobe o HBase fora do `docker-compose`.
- **`seed_data.py`** — popula 4 sensores, 2 atuadores e 10 leituras
  cada para você ter dados de demonstração imediatamente.
- **`smoke_test.ps1`** — bateria de chamadas HTTP via PowerShell que
  exercita todos os endpoints (pode rodar contra `localhost` ou
  contra a URL pública de produção).

## 10. Como rodar sem HBase nem Docker

Esta é a forma mais rápida para validar o trabalho:

### Opção A — apenas pytest (não precisa nem subir servidor)

```powershell
pip install -r requirements.txt
pytest -q
```

O fixture já define `USE_INMEMORY_DB=1` e usa o **test client** do
Flask (`app.test_client()`), que invoca a aplicação **sem abrir
socket** — ótimo para CI e para depurar com breakpoints.

### Opção B — servidor real, banco em memória

```powershell
pip install -r requirements.txt
$env:USE_INMEMORY_DB="1"
python run.py
```

Em outra janela:

```powershell
# Smoke test completo
.\scripts\smoke_test.ps1

# ou um único endpoint
curl http://localhost:5000/health
```

Limitações do modo em memória:
- Dados são perdidos ao reiniciar o processo.
- Se rodar com Gunicorn em modo multi-worker, cada worker tem seu
  próprio dicionário → use `gunicorn -w 1 …` ao testar.

### Opção C — tudo de verdade

```powershell
docker compose up --build
docker compose exec api python -m scripts.seed_data
```

## 11. Tratamento de erros — convenções

| Situação                              | Status | Corpo |
|---------------------------------------|--------|-------|
| Campo obrigatório ausente             | 400    | `{"erro": "..."}` |
| Recurso não encontrado                | 404    | `{"erro": "..."}` |
| Comando inválido para atuador         | 400    | `{"status":"falha","mensagem":...}` |
| Falha em webservice externo           | 502    | `{"status":"falha","mensagem":...}` |
| Exceção não tratada                   | 500    | `{"erro":"erro interno do servidor"}` |

Toda resposta é JSON, mesmo erros, para facilitar consumo automatizado.

## 12. Por que HBase?

- **Esquema flexível por família** — cada linha pode ter colunas
  diferentes, o que combina com a heterogeneidade de dispositivos IoT.
- **Escrita otimizada** (LSM-trees) — segura picos de telemetria.
- **Row keys ordenadas** — viabiliza scans muito eficientes por
  prefixo, exatamente o padrão usado nas leituras.

## 13. Próximos passos sugeridos (não implementados)

- Autenticação por token (JWT ou API key).
- Paginação real nos listings (HBase START/STOP rowkey).
- Stream de leituras via WebSocket / SSE.
- Front-end de dashboard consumindo a API.
