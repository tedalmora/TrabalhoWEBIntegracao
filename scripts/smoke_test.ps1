# Smoke test da API via PowerShell — executa todos os endpoints principais.
#
# Pré-requisito: a API precisa estar rodando. Para subir SEM HBase:
#
#   $env:USE_INMEMORY_DB="1"
#   python run.py
#
# Em outra janela:
#   .\scripts\smoke_test.ps1
#
# Aceita parâmetro opcional -BaseUrl para apontar para uma URL pública:
#   .\scripts\smoke_test.ps1 -BaseUrl "https://iot-api.onrender.com"

param(
    [string]$BaseUrl = "http://localhost:5000"
)

$ErrorActionPreference = "Stop"

function Show($titulo, $obj) {
    Write-Host "`n==> $titulo" -ForegroundColor Cyan
    $obj | ConvertTo-Json -Depth 6
}

Write-Host "Smoke test contra $BaseUrl" -ForegroundColor Green

Show "1. Index" (Invoke-RestMethod "$BaseUrl/")
Show "2. Health" (Invoke-RestMethod "$BaseUrl/health")

# Sensor
$novo = Invoke-RestMethod -Method Post "$BaseUrl/sensores" -ContentType "application/json" `
    -Body (@{ tipo = "temperatura"; localizacao = "Sala 101" } | ConvertTo-Json)
Show "3. Cria sensor" $novo
$sid = $novo.id

Show "4. Busca por chave (Req 3)" (Invoke-RestMethod "$BaseUrl/sensores/$sid")

# Envio de leituras
1..3 | ForEach-Object {
    $payload = @{ valor = (Get-Random -Minimum 18 -Maximum 32); unidade = "C" } | ConvertTo-Json
    Invoke-RestMethod -Method Post "$BaseUrl/sensores/$sid/dados" -ContentType "application/json" -Body $payload | Out-Null
}
Show "5. Leituras do sensor" (Invoke-RestMethod "$BaseUrl/sensores/$sid/dados")

Show "6. Lista filtrada (Req 5)" (Invoke-RestMethod "$BaseUrl/sensores?tipo=temperatura")
Show "7. Leituras com faixa (Req 5)" (Invoke-RestMethod "$BaseUrl/leituras?sensor_id=$sid&valor_min=10")

# Atuador
$atu = Invoke-RestMethod -Method Post "$BaseUrl/atuadores" -ContentType "application/json" `
    -Body (@{ nome = "Lampada"; tipo = "lampada" } | ConvertTo-Json)
$aid = $atu.id
Show "8. Cria atuador" $atu

Show "9. Comando LIGAR (Req 2)" (Invoke-RestMethod -Method Post "$BaseUrl/atuadores/$aid/comando" `
    -ContentType "application/json" -Body (@{ comando = "LIGAR" } | ConvertTo-Json))

Show "10. Comando inválido — deve falhar" (
    try {
        Invoke-RestMethod -Method Post "$BaseUrl/atuadores/$aid/comando" `
            -ContentType "application/json" -Body (@{ comando = "EXPLODIR" } | ConvertTo-Json)
    } catch { $_.ErrorDetails.Message }
)

# API externa — só roda se OPENWEATHER_API_KEY estiver configurada
Write-Host "`n==> 11. Webservice externo (Req 4) — pode falhar se sem OPENWEATHER_API_KEY" -ForegroundColor Yellow
try {
    Invoke-RestMethod "$BaseUrl/clima?cidade=Curitiba,BR" | ConvertTo-Json -Depth 6
} catch {
    Write-Host "   (esperado se chave não configurada): $($_.ErrorDetails.Message)" -ForegroundColor DarkYellow
}

Write-Host "`nSmoke test concluído com sucesso." -ForegroundColor Green
