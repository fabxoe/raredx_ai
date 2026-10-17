$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = "C:\raredx\app"
$AppTask = "RareDX-App"
$AppUrl = "http://127.0.0.1:8010/"
$MapperUrl = "http://127.0.0.1:8010/api/hpo-mappers"
$GitExe = "C:\Program Files\Git\cmd\git.exe"
$UvExe = "C:\Program Files\uv\uv.exe"

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
if (-not (Test-Path $GitExe)) {
    throw "Git executable not found: $GitExe"
}
if (-not (Test-Path $UvExe)) {
    throw "uv executable not found: $UvExe"
}

Set-Location $RepoDir
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

& $GitExe -c "safe.directory=$RepoDir" fetch origin main
& $GitExe -c "safe.directory=$RepoDir" checkout main
& $GitExe -c "safe.directory=$RepoDir" pull --ff-only origin main

& $UvExe sync --locked --python 3.12 --extra dev
& $UvExe run pytest -q

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
