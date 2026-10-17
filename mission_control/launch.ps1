param([ValidateRange(1024,65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$systemPython = (Get-Command python -ErrorAction Stop).Source
& $systemPython -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'WMM requires Python 3.11 or newer.' }
$venvRoot = Join-Path $projectRoot '.venv'
$pythonPath = Join-Path $venvRoot 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & $systemPython -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw 'Python environment setup failed. Install Python 3.11+ with venv and pip support.' }
}
& $pythonPath -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'The existing .venv uses an older Python. Select a Python 3.11+ environment before starting WMM.' }
& $pythonPath -m pip install --disable-pip-version-check --require-hashes --only-binary :all: -r (Join-Path $projectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Timezone setup failed. Check internet access and retry; existing workspaces are preserved.' }
$databasePath = Join-Path $PSScriptRoot 'data/mission-control.sqlite3'
$workspaceInstanceId = & $pythonPath -c "import hashlib,pathlib,sys; print(hashlib.sha256(str(pathlib.Path(sys.argv[1]).resolve()).casefold().encode()).hexdigest()[:24])" $databasePath
if ($LASTEXITCODE -ne 0) { throw 'Could not identify this local workspace.' }
$taskHealthUrl = "http://127.0.0.1:$Port/api/bootstrap"
try {
    $taskHealth = Invoke-RestMethod -Uri $taskHealthUrl -TimeoutSec 2
    if ($taskHealth.mode -ne 'LOCAL_WORKSTATION' -or $taskHealth.workspace_instance_id -ne $workspaceInstanceId) { throw 'Port belongs to another application or workspace.' }
} catch {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) { throw "Port $Port is already occupied. Choose another port; existing processes were preserved." }
    Start-Process -FilePath $pythonPath -ArgumentList @('-X', 'utf8', '-m', 'mission_control.server', '--port', $Port) -WorkingDirectory $projectRoot -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 250
        try {
            $taskHealth = Invoke-RestMethod -Uri $taskHealthUrl -TimeoutSec 2
            if ($taskHealth.mode -eq 'LOCAL_WORKSTATION' -and $taskHealth.workspace_instance_id -eq $workspaceInstanceId) { break }
        } catch { }
    }
    if ($taskHealth.mode -ne 'LOCAL_WORKSTATION' -or $taskHealth.workspace_instance_id -ne $workspaceInstanceId) { throw 'WMM did not start. Run .venv\Scripts\python.exe -m mission_control.server to inspect its error.' }
}
Start-Process "http://127.0.0.1:$Port/"
