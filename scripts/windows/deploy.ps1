$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = "C:\raredx\app"
$AppTask = "RareDX-App"
$AppUrl = "http://127.0.0.1:8010/"
$MapperUrl = "http://127.0.0.1:8010/api/hpo-mappers"

function Wait-HttpOk {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$Attempts = 30
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                Write-Host "$Url OK"
                return
            }
        }
        catch {
            if ($attempt -eq $Attempts) {
                throw "Health check failed after $Attempts attempts: $Url"
            }
        }
        Start-Sleep -Seconds 2
    }
}

if (-not (Test-Path (Join-Path $RepoDir ".git"))) {
    throw "Deployment repository not found: $RepoDir"
}
if (-not (Test-Path (Join-Path $RepoDir ".env"))) {
    throw "Server environment file not found: $RepoDir\.env"
}

Set-Location $RepoDir
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

git fetch origin main
git checkout main
git pull --ff-only origin main

uv sync --locked --python 3.12 --extra dev
uv run pytest -q

$neo4j = Get-Service neo4j -ErrorAction Stop
if ($neo4j.Status -ne "Running") {
    Start-Service neo4j
}
Wait-HttpOk -Url "http://127.0.0.1:7474/"

if (-not (Get-ScheduledTask -TaskName $AppTask -ErrorAction SilentlyContinue)) {
    throw "Scheduled task not found: $AppTask"
}

Stop-ScheduledTask -TaskName $AppTask -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName $AppTask

Wait-HttpOk -Url $AppUrl
Wait-HttpOk -Url $MapperUrl

Write-Host "Windows deployment completed successfully."
