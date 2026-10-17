param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$taskHealthUrl = "http://127.0.0.1:$Port/api/bootstrap"
try {
    $taskHealth = Invoke-RestMethod -Uri $taskHealthUrl -TimeoutSec 2
    if ($taskHealth.mode -ne 'LOCAL_WORKSTATION') { throw 'Port belongs to another application.' }
} catch {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) { throw "Port $Port is already occupied. Choose another port; existing processes were preserved." }
    Start-Process -FilePath $pythonPath -ArgumentList @('-X', 'utf8', '-m', 'mission_control.server', '--port', $Port) -WorkingDirectory $projectRoot -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 250
        try {
            $taskHealth = Invoke-RestMethod -Uri $taskHealthUrl -TimeoutSec 2
            if ($taskHealth.mode -eq 'LOCAL_WORKSTATION') { break }
        } catch { }
    }
    if ($taskHealth.mode -ne 'LOCAL_WORKSTATION') { throw 'Mission Control did not start. Run python -m mission_control.server to inspect its error.' }
}
Start-Process "http://127.0.0.1:$Port/"
