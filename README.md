# Sistema de Gerência de Sensores IoT — Flask + Apache HBase

API REST em **Python/Flask** para um sistema de monitoramento e controle de
dispositivos IoT (sensores e atuadores) com persistência em **Apache HBase**
(via [HappyBase](https://happybase.readthedocs.io/) sobre Thrift) e
integração com **OpenWeatherMap** e **ThingSpeak**.

> Trabalho de Webservices — atende aos itens 1 a 6 do enunciado.

---

## 1. Sumário dos requisitos atendidos

| Req | Onde está | Observação |
|---|---|---|
| 1. Contexto, arquitetura e diagramas | [docs/CONTEXTO.md](docs/CONTEXTO.md), [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | REST + JSON sobre HTTP |
| 2. Webservice com envio de comando e status | `POST /atuadores/<id>/comando` em [app/routes/atuadores.py](app/routes/atuadores.py) | retorna `status: sucesso/falha` |
| 3. Busca por chave | `GET /sensores/<id>` em [app/routes/sensores.py](app/routes/sensores.py) | rowkey HBase |
| 4. Webservice de terceiros | `GET /clima?cidade=...` em [app/routes/clima.py](app/routes/clima.py) | OpenWeatherMap + ThingSpeak |
| 5. Lista com filtro | `GET /sensores?tipo=temperatura&localizacao=Sala` e `GET /leituras?sensor_id=...&valor_min=...` | filtros server-side |
| 6. Banco de dados | Apache HBase (NoSQL colunar) via [app/database.py](app/database.py) | Docker local |

---

## 2. Tecnologias

- **Linguagem:** Python 3.11
- **Framework Web:** Flask 3 + Flask-CORS, servido por Gunicorn em produção
- **Banco NoSQL:** Apache HBase (standalone) com Thrift na porta 9090
- **Cliente HBase:** HappyBase
- **HTTP client externo:** Requests
- **Container:** Docker / Docker Compose
- **APIs externas:** OpenWeatherMap (clima), ThingSpeak (envio de leitura)
- **Testes:** Pytest

---

## 3. Estrutura do projeto

```
TrabalhoWEBIntegracao/
├── app/
│   ├── __init__.py          # factory Flask
│   ├── config.py            # variáveis de ambiente
│   ├── database.py          # conexão e bootstrap das tabelas HBase
│   ├── routes/
│   │   ├── sensores.py      # CRUD de sensores + leituras
│   │   ├── atuadores.py     # CRUD e comandos para atuadores
│   │   ├── leituras.py      # busca global de leituras com filtros
│   │   └── clima.py         # integração com OpenWeatherMap/ThingSpeak
│   ├── services/
│   │   ├── openweather_service.py
│   │   └── thingspeak_service.py
│   └── utils/helpers.py
├── scripts/
│   ├── init_hbase.py        # cria tabelas
│   └── seed_data.py         # popula dados de exemplo
├── tests/test_api.py
├── docs/
│   ├── CONTEXTO.md          # entrega da primeira semana
│   ├── ARQUITETURA.md       # diagramas Mermaid
│   └── postman_collection.json
├── docker-compose.yml       # sobe HBase + API
├── Dockerfile
├── render.yaml              # deploy no Render.com
├── Procfile                 # deploy no Heroku/Railway
├── requirements.txt
└── run.py
```

---

## 4. Como executar localmente

### 4.0. Modo "sem Docker e sem HBase" (para testar rapidinho)

Foi incluído um **backend em memória** que imita a interface do HBase.
Basta exportar `USE_INMEMORY_DB=1`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:USE_INMEMORY_DB="1"
python run.py
```

Em outra janela, rode o smoke test que cobre todos os endpoints:

```powershell
.\scripts\smoke_test.ps1
```

E os testes unitários (não precisam nem do servidor aberto):

```powershell
pip install pytest
pytest -q
```

> Limitação: os dados ficam apenas em memória — reiniciar o processo
> zera tudo. Para persistência real use o modo Docker abaixo.

### 4.1. Subir tudo com Docker Compose (recomendado)

```powershell
copy .env.example .env
# edite .env e coloque sua OPENWEATHER_API_KEY
docker compose up --build
```

A API ficará em <http://localhost:5000> e a UI do HBase em <http://localhost:16010>.

Na **primeira inicialização** as tabelas são criadas automaticamente pelo
`app/__init__.py`. Para popular dados de exemplo:

```powershell
docker compose exec api python -m scripts.seed_data
```

### 4.2. Rodar apenas o HBase via Docker e a API local

```powershell
# 1. HBase isolado
docker run -d --name iot_hbase -p 9090:9090 -p 16010:16010 dajobe/hbase

# 2. Ambiente Python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env

# 3. Cria tabelas e popula
python -m scripts.init_hbase
python -m scripts.seed_data

# 4. Sobe a API
python run.py
```

### 4.3. Testes

```powershell
pip install pytest
pytest -q
```

Os testes usam o **backend em memória** automaticamente, então rodam
sem precisar de HBase nem Docker.

---

## 5. Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET    | `/`                                | Lista todos os endpoints |
| GET    | `/health`                          | Health check API + HBase |
| POST   | `/sensores`                        | Cria sensor |
| GET    | `/sensores`                        | Lista (filtros `tipo`, `localizacao`) |
| GET    | `/sensores/<id>`                   | Busca por chave |
| PUT    | `/sensores/<id>`                   | Atualiza |
| DELETE | `/sensores/<id>`                   | Remove |
| POST   | `/sensores/<id>/dados`             | Envia leitura |
| GET    | `/sensores/<id>/dados`             | Leituras do sensor |
| POST   | `/atuadores`                       | Cria atuador |
| GET    | `/atuadores`                       | Lista (filtros `tipo`, `estado`) |
| GET    | `/atuadores/<id>`                  | Busca atuador |
| POST   | `/atuadores/<id>/comando`          | **Envia comando, retorna status** |
| GET    | `/leituras`                        | Lista filtrada de leituras |
| GET    | `/clima?cidade=Curitiba,BR`        | **Consulta API externa OpenWeatherMap** |
| POST   | `/clima/sincronizar/<sensor_id>`   | Pega clima e grava como leitura (+ envia ao ThingSpeak) |

### 5.1. Exemplos com `curl`

```powershell
# criar sensor
curl -X POST http://localhost:5000/sensores `
  -H "Content-Type: application/json" `
  -d '{"tipo":"temperatura","localizacao":"Sala 101"}'

# enviar leitura
curl -X POST http://localhost:5000/sensores/sen_temp_01/dados `
  -H "Content-Type: application/json" `
  -d '{"valor":24.7,"unidade":"C"}'

# listar com filtro (Req. 5)
curl "http://localhost:5000/sensores?tipo=temperatura"

# busca por chave (Req. 3)
curl http://localhost:5000/sensores/sen_temp_01

# comando para atuador (Req. 2)
curl -X POST http://localhost:5000/atuadores/atu_lamp_01/comando `
  -H "Content-Type: application/json" `
  -d '{"comando":"LIGAR"}'

# webservice externo (Req. 4)
curl "http://localhost:5000/clima?cidade=Curitiba,BR"
```

---

## 6. Deploy público

Três caminhos prontos:

### 6.1. Render.com (gratuito)
1. Crie conta em <https://render.com>.
2. **New > Blueprint** apontando para este repositório → o arquivo
   [`render.yaml`](render.yaml) é detectado automaticamente.
3. Configure as variáveis `OPENWEATHER_API_KEY`, `HBASE_HOST`, etc. no painel.
4. Como o HBase exige Thrift TCP, hospede-o em:
   - uma VM (Oracle Cloud Free Tier, AWS EC2 t2.micro) executando
     `docker run -d -p 9090:9090 dajobe/hbase`;
   - aponte `HBASE_HOST` para o IP público dessa VM.

### 6.2. Railway / Fly.io
- Use o `Dockerfile` deste repositório (`fly launch` ou Railway "Deploy from Repo").

### 6.3. Heroku
- `Procfile` já incluso. `heroku create` + `git push heroku main`.

> Para o trabalho, qualquer URL pública (`https://iot-api-flask.onrender.com/`)
> que responda aos endpoints acima atende ao item de "URL com o serviço
> funcionando em local acessível na Internet".

---

## 7. Modelo de dados no HBase

| Tabela            | Row key                            | Famílias / Colunas |
|-------------------|------------------------------------|--------------------|
| `iot_sensores`    | `sen_<uuid>`                       | `info:tipo`, `info:localizacao`, `info:descricao`, `info:criado_em` |
| `iot_atuadores`   | `atu_<uuid>`                       | `info:nome`, `info:tipo`, `info:localizacao`, `estado:atual`, `estado:atualizado_em` |
| `iot_leituras`    | `<sensor_id>#<reverse_timestamp>`  | `dados:sensor_id`, `dados:valor`, `dados:unidade`, `dados:timestamp` |

O timestamp invertido na rowkey das leituras faz o `scan` por `row_prefix`
retornar as leituras mais recentes primeiro — útil para dashboards.

---

## 8. Documentação adicional

- [docs/CONTEXTO.md](docs/CONTEXTO.md) — entrega da semana 1
- [docs/ARQUITETURA.md](docs/ARQUITETURA.md) — diagramas Mermaid
- [docs/EXPLICACAO_CODIGO.md](docs/EXPLICACAO_CODIGO.md) — **explicação detalhada do código, arquivo por arquivo**
- [docs/APRESENTACAO.md](docs/APRESENTACAO.md) — roteiro de apresentação
- [docs/postman_collection.json](docs/postman_collection.json)

---

## 9. Licença

Uso acadêmico. Sinta-se à vontade para reaproveitar.
