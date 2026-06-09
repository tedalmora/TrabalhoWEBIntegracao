# Diagramas de Arquitetura e Sequência

## Arquitetura geral

```mermaid
flowchart TB
    subgraph Edge["Camada de Dispositivos"]
        S1[Sensor de Temperatura]
        S2[Sensor de Umidade]
        A1[Atuador / Lâmpada]
    end

    subgraph Cloud["Camada de Aplicação"]
        API["API Flask<br/>Gunicorn"]
    end

    subgraph Data["Camada de Dados"]
        HB[(Apache HBase<br/>Thrift 9090)]
    end

    subgraph Ext["APIs Externas"]
        OW[OpenWeatherMap]
        TS[ThingSpeak]
    end

    S1 -- HTTP POST --> API
    S2 -- HTTP POST --> API
    A1 <-- HTTP --> API
    API -- HappyBase --> HB
    API -- HTTPS --> OW
    API -- HTTPS --> TS
```

## Sequência — envio de leitura por um sensor

```mermaid
sequenceDiagram
    autonumber
    participant Sensor
    participant API as Flask API
    participant HB as HBase
    Sensor->>API: POST /sensores/{id}/dados {valor, unidade}
    API->>HB: row.put(sensor_id#~ts, {dados:valor,...})
    HB-->>API: ack
    API-->>Sensor: 201 {status: sucesso, timestamp}
```

## Sequência — comando para atuador

```mermaid
sequenceDiagram
    autonumber
    participant Cli as Cliente
    participant API as Flask API
    participant HB as HBase
    Cli->>API: POST /atuadores/{id}/comando {comando:"LIGAR"}
    API->>HB: row(atuador_id) [busca atual]
    HB-->>API: row existente
    API->>HB: row.put(atuador_id, estado:atual="LIGADO")
    HB-->>API: ack
    API-->>Cli: 200 {status:sucesso, estado_atual:"LIGADO"}
```

## Sequência — integração com webservice externo

```mermaid
sequenceDiagram
    autonumber
    participant Cli as Cliente
    participant API as Flask API
    participant OW as OpenWeatherMap
    participant TS as ThingSpeak
    participant HB as HBase
    Cli->>API: POST /clima/sincronizar/{sensor_id}
    API->>OW: GET /weather?q=Curitiba,BR&units=metric
    OW-->>API: {main.temp, main.humidity, ...}
    API->>HB: leituras.put(sensor#~ts, valor=temp)
    HB-->>API: ack
    alt ThingSpeak configurado
        API->>TS: POST /update.json field1=temp field2=humidity
        TS-->>API: entry_id
    end
    API-->>Cli: 200 {status:sucesso, leitura, thingspeak}
```

## Sequência — busca filtrada de leituras

```mermaid
sequenceDiagram
    autonumber
    participant Cli as Cliente
    participant API as Flask API
    participant HB as HBase
    Cli->>API: GET /leituras?sensor_id=sen_temp_01&valor_min=20
    API->>HB: scan(row_prefix="sen_temp_01#", limit=100)
    HB-->>API: rows
    API-->>API: filtra por valor_min/unidade
    API-->>Cli: 200 {total, leituras:[...]}
```
