# Roteiro de Apresentação — Sistema de Gerência de Sensores IoT

> Sugestão de roteiro para a apresentação em sala (10–15 min).

## 1. Abertura (1 min)
- Nome do projeto: **Sistema de Gerência de Sensores IoT**
- Stack: **Flask (Python) + Apache HBase**
- Atende aos 6 requisitos do enunciado.

## 2. Contexto e motivação (2 min)
- Cenário: monitoramento de sensores e atuadores distribuídos.
- Por que **REST + JSON**: simplicidade, ubíquo, fácil teste.
- Por que **HBase**: NoSQL colunar, alta taxa de escrita, ideal para
  dados históricos de IoT.

## 3. Arquitetura (2 min)
- Mostrar o diagrama de [docs/ARQUITETURA.md](ARQUITETURA.md).
- Fluxo: Sensor → API Flask → HBase. APIs externas para enriquecimento.

## 4. Modelo de dados (1 min)
- 3 tabelas: `iot_sensores`, `iot_atuadores`, `iot_leituras`.
- Famílias de colunas: `info`, `estado`, `dados`.
- Row key de leituras com timestamp invertido para scan eficiente.

## 5. Demonstração ao vivo (5 min)
Sequência sugerida (com Postman ou `curl`):

1. `GET /health` — mostrar API + HBase OK.
2. `POST /sensores` — cria sensor.
3. `GET /sensores/<id>` — **Req. 3** (busca por chave).
4. `POST /sensores/<id>/dados` — envia leitura.
5. `GET /sensores?tipo=temperatura` — **Req. 5** (lista com filtro).
6. `POST /atuadores/<id>/comando` com `{"comando":"LIGAR"}` —
   **Req. 2** (envio + status sucesso/falha).
7. `GET /clima?cidade=Curitiba,BR` — **Req. 4** (API de terceiros).
8. `POST /clima/sincronizar/<sensor_id>` — usa OpenWeatherMap para
   gerar leitura e (se configurado) envia ao ThingSpeak.

## 6. Deploy público (1 min)
- Mostrar URL ativa (Render/Railway/Heroku) e os mesmos requests
  funcionando contra a Internet.

## 7. Encerramento (1 min)
- Repositório no GitHub.
- Próximos passos: autenticação JWT, websockets para streaming, dashboard
  com gráficos das leituras.
