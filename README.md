# Sistema de Gerência de Sensores IoT — Flask + HBase

API REST simples em Python/Flask para um sistema de monitoramento e
controle de dispositivos IoT (sensores e atuadores), com persistência
em **Apache HBase** e integração com **OpenWeatherMap**.

> Trabalho de Webservices.

## Estrutura

```
TrabalhoWEBIntegracao/
├── app.py             ← API completa (rotas + banco + integrações)
├── docs/
│   └── EXPLICACAO_CODIGO.md  ← explicação do que cada parte do código faz
├── requirements.txt   ← dependências Python
└── .env               ← configuração (criar — ver "Configuração" abaixo)
```

## Documento de explicação

Explicação do código e de cada parte em:
- `docs/EXPLICACAO_CODIGO.md`

## Requisitos atendidos

| Req | Onde |
|---|---|
| 2 — envio com status sucesso/falha | `POST /atuadores/<id>/comando` |
| 3 — busca por chave                 | `GET /sensores/<id>` |
| 4 — webservice de terceiros         | `GET /clima?cidade=Curitiba,BR` (OpenWeatherMap) |
| 5 — lista com filtro                | `GET /sensores?tipo=...`, `GET /leituras?sensor_id=...&valor_min=...` |
| 6 — banco                           | Apache HBase (NoSQL colunar) |

## Configuração

Crie um arquivo `.env` na raiz:

```
HBASE_HOST=localhost
HBASE_PORT=9090
HBASE_TABLE_PREFIX=iot
OPENWEATHER_API_KEY=coloque-sua-chave-aqui

# Para testar SEM HBase (usa banco em memória):
USE_INMEMORY_DB=0
```

Pegue uma chave grátis em <https://openweathermap.org/api>.

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> Se `happybase` falhar de instalar (acontece no Python 3.14 sem `setuptools`):
> ```
> pip install setuptools
> pip install -r requirements.txt
> ```
> Ou, se for usar **só** o modo em memória, basta comentar a linha `happybase` no `requirements.txt`.

## Rodar

### Com HBase real (Docker local)

```powershell
docker run -d --name iot_hbase -p 9090:9090 -p 16010:16010 dajobe/hbase
python app.py
```

API em <http://localhost:5000>. UI do HBase em <http://localhost:16010>.

### Sem HBase (modo em memória, ótimo para testar rápido)

```powershell
$env:USE_INMEMORY_DB="1"
python app.py
```

## Endpoints

| Método | Rota                              | Descrição |
|--------|-----------------------------------|-----------|
| GET    | `/`                               | catálogo |
| GET    | `/health`                         | status API + banco |
| POST   | `/sensores`                       | cria sensor |
| GET    | `/sensores?tipo=&localizacao=`    | lista com filtro |
| GET    | `/sensores/<id>`                  | busca por chave |
| PUT    | `/sensores/<id>`                  | atualiza |
| DELETE | `/sensores/<id>`                  | remove |
| POST   | `/sensores/<id>/dados`            | envia leitura |
| GET    | `/sensores/<id>/dados`            | leituras do sensor |
| GET    | `/leituras?sensor_id=&valor_min=` | lista global filtrada |
| POST   | `/atuadores`                      | cria atuador |
| GET    | `/atuadores`                      | lista |
| GET    | `/atuadores/<id>`                 | busca |
| POST   | `/atuadores/<id>/comando`         | envia comando (sucesso/falha) |
| GET    | `/clima?cidade=Curitiba,BR`       | OpenWeatherMap |

### Exemplos com `curl.exe` (PowerShell)

Use **`curl.exe`** e **aspas simples** no PowerShell — `curl` puro é alias do `Invoke-WebRequest`.

```powershell
# cria sensor
curl.exe -X POST http://localhost:5000/sensores -H "Content-Type: application/json" -d '{"id":"sen_temp_01","tipo":"temperatura","localizacao":"Sala 101"}'

# envia leitura
curl.exe -X POST http://localhost:5000/sensores/sen_temp_01/dados -H "Content-Type: application/json" -d '{"valor":24.7,"unidade":"C"}'

# busca por chave (Req. 3)
curl.exe http://localhost:5000/sensores/sen_temp_01

# lista com filtro (Req. 5)
curl.exe "http://localhost:5000/sensores?tipo=temperatura"

# cria atuador + comando (Req. 2)
curl.exe -X POST http://localhost:5000/atuadores -H "Content-Type: application/json" -d '{"id":"atu_lamp_01","nome":"Lampada","tipo":"lampada"}'
curl.exe -X POST http://localhost:5000/atuadores/atu_lamp_01/comando -H "Content-Type: application/json" -d '{"comando":"LIGAR"}'

# webservice externo (Req. 4)
curl.exe "http://localhost:5000/clima?cidade=Curitiba,BR"
```

## Modelo de dados no HBase

| Tabela          | Row key                           | Famílias / Colunas |
|-----------------|-----------------------------------|--------------------|
| `iot_sensores`  | `sen_<uuid>`                      | `info:tipo`, `info:localizacao`, `info:descricao`, `info:criado_em` |
| `iot_atuadores` | `atu_<uuid>`                      | `info:nome`, `info:tipo`, `info:localizacao`, `estado:atual`, `estado:atualizado_em` |
| `iot_leituras`  | `<sensor_id>#<reverse_timestamp>` | `dados:sensor_id`, `dados:valor`, `dados:unidade`, `dados:timestamp` |

O timestamp invertido na row key (`10^13 - ts`) faz com que um `scan` por
prefixo devolva as leituras mais recentes primeiro.
