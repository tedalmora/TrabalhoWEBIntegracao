# Explicação do Código (versão simplificada)

Este projeto foi simplificado para 1 arquivo principal: `app.py`.

## Arquivos

- `app.py`: API completa (rotas, banco, integração externa, erros)
- `requirements.txt`: dependências Python
- `.env`: configuração local
- `README.md`: guia de instalação e uso

## Como o `app.py` está organizado

### 1) Configuração (topo do arquivo)
Lê variáveis de ambiente:
- `HBASE_HOST`, `HBASE_PORT`, `HBASE_TABLE_PREFIX`
- `USE_INMEMORY_DB` (liga modo em memória)
- `OPENWEATHER_API_KEY`

Também monta os nomes das tabelas:
- `iot_sensores`
- `iot_atuadores`
- `iot_leituras`

### 2) Camada de dados
Existem dois modos:

- **HBase real** (HappyBase)
- **Em memória** (dict Python), útil para testes rápidos

A função `conexao()` decide automaticamente qual usar.

### 3) Inicialização de tabelas
`init_tabelas()` cria tabelas/famílias caso não existam:
- sensores: família `info`
- atuadores: famílias `info`, `estado`
- leituras: família `dados`

### 4) Helpers
- `gerar_id(prefixo)`: gera id curto (`sen_xxx`, `atu_xxx`)
- `agora_ms()`: timestamp em ms
- `to_hbase()`: converte dict para formato de colunas HBase
- `from_hbase()`: converte de volta para JSON simples

### 5) Endpoints da API

#### Base
- `GET /`: lista endpoints
- `GET /health`: status de API + banco

#### Sensores
- `POST /sensores`: cria sensor
- `GET /sensores`: lista com filtro (`tipo`, `localizacao`)
- `GET /sensores/<id>`: busca por chave
- `PUT /sensores/<id>`: atualiza
- `DELETE /sensores/<id>`: remove
- `POST /sensores/<id>/dados`: adiciona leitura
- `GET /sensores/<id>/dados`: lista leituras de um sensor

#### Leituras
- `GET /leituras`: lista global com filtros (`sensor_id`, `valor_min`, `valor_max`, `unidade`)

#### Atuadores
- `POST /atuadores`: cria atuador
- `GET /atuadores`: lista com filtro (`tipo`, `estado`)
- `GET /atuadores/<id>`: busca por chave
- `POST /atuadores/<id>/comando`: aplica comando (`LIGAR`, `DESLIGAR`, etc.) e retorna sucesso/falha

#### Serviço externo
- `GET /clima?cidade=...`: consulta OpenWeatherMap

### 6) Tratamento de erros
- 400, 404 e 500 retornam sempre JSON padronizado

## Fluxo típico de uso
1. Criar sensor (`POST /sensores`)
2. Enviar leitura (`POST /sensores/<id>/dados`)
3. Consultar sensor (`GET /sensores/<id>`)
4. Consultar leituras (`GET /sensores/<id>/dados` ou `GET /leituras`)
5. Criar atuador e enviar comando (`POST /atuadores`, `POST /atuadores/<id>/comando`)

## Observação importante
No PowerShell, use `curl.exe` (não `curl`) para evitar conflito de alias.
