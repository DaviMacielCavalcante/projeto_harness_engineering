param(
    [string]$Gateway = "http://localhost:8000",
    [string]$OutDir = "data/exp4",
    [string]$OutFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($OutFile -eq "") {
    $OutFile = Join-Path $OutDir "chaos.txt"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Set-Content -Path $OutFile -Value "" -Encoding UTF8

function Write-ChaosLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format o), $Message
    $line | Out-File -FilePath $OutFile -Append -Encoding UTF8
    $line
}

function Add-Output {
    param([string[]]$Lines)
    foreach ($line in $Lines) {
        $line | Out-File -FilePath $OutFile -Append -Encoding UTF8
        $line
    }
}

function Invoke-QueryOnce {
    param([string]$Question = "Sobre o que fala o corpus?")

    $body = @{
        question = $Question
        top_k = 3
    } | ConvertTo-Json -Compress

    $started = Get-Date
    try {
        $response = Invoke-WebRequest -Uri "$Gateway/query" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 180
        $status = [int]$response.StatusCode
    }
    catch {
        $status = 0
    }
    $elapsed = ((Get-Date) - $started).TotalSeconds
    "status={0} time={1:N3}" -f $status, $elapsed
}

Write-ChaosLog "chaos.start gateway=$Gateway"

Write-ChaosLog "H1 stop rag-ingest-worker-chunk"
Add-Output (docker stop rag-ingest-worker-chunk)
Start-Sleep -Seconds 5
Add-Output (docker start rag-ingest-worker-chunk)
Write-ChaosLog "H1 done"

Write-ChaosLog "H2 stop rag-ollama"
Add-Output (docker stop rag-ollama)
Add-Output (Invoke-QueryOnce "Teste de resiliencia com Ollama parado")
Add-Output (docker start rag-ollama)
Write-ChaosLog "H2 done"

Write-ChaosLog "H3 burst queries"
$jobs = 1..10 | ForEach-Object {
    Start-Job -ScriptBlock {
        param($GatewayUrl, $Index)
        $body = @{
            question = "Pergunta concorrente $Index sobre engenharia de software"
            top_k = 3
        } | ConvertTo-Json -Compress
        $started = Get-Date
        try {
            $response = Invoke-WebRequest -Uri "$GatewayUrl/query" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 180
            $status = [int]$response.StatusCode
        }
        catch {
            $status = 0
        }
        $elapsed = ((Get-Date) - $started).TotalSeconds
        "status={0} time={1:N3}" -f $status, $elapsed
    } -ArgumentList $Gateway, $_
}

($jobs | Wait-Job | Receive-Job) | Out-File -FilePath $OutFile -Append -Encoding UTF8
$jobs | Remove-Job
Write-ChaosLog "H3 done"

Write-ChaosLog "chaos.done out=$OutFile"
Copy-Item -Path $OutFile -Destination "data/b3-chaos.txt" -Force
