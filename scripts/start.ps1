param([switch]$Install)
$ErrorActionPreference='Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if ($Install) {
    python -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install -r requirements.lock
}
$python=if (Test-Path .\.venv\Scripts\python.exe) {'.\.venv\Scripts\python.exe'} elseif (Test-Path ..\.venv\Scripts\python.exe) {'..\.venv\Scripts\python.exe'} else {throw 'Run scripts/start.ps1 -Install first'}
$env:PYTHONUTF8='1'
# Load only known settings; never execute .env contents as shell commands.
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^(FKG_DATA_DIR|FKG_IMPORT_ROOTS|OPENCODE_URL|OPENCODE_DIRECTORY|OPENCODE_PASSWORD|PYTHONUTF8)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1],$matches[2],'Process')
        }
    }
}
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
