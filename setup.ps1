param([switch]$Transcription)
$ErrorActionPreference='Stop'
$taskRoot=$PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskCache=Join-Path $taskRoot 'work/cache'
$taskTemp=Join-Path $taskCache 'tmp'
New-Item -ItemType Directory -Path $taskTemp -Force | Out-Null
$env:TEMP=$taskTemp
$env:TMP=$taskTemp
$env:PIP_CACHE_DIR=Join-Path $taskCache 'pip'
$env:npm_config_cache=Join-Path $taskCache 'npm'
$env:PNPM_HOME=Join-Path $taskCache 'pnpm'
$env:COREPACK_HOME=Join-Path $taskCache 'corepack'
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Creazione venv fallita' }
$taskPython=Join-Path $taskRoot '.venv/Scripts/python.exe'
& $taskPython -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Installazione dipendenze Python fallita' }
if ($Transcription) {
    & $taskPython -m pip install -r requirements-transcription.txt
    if ($LASTEXITCODE -ne 0) { throw 'Installazione trascrizione fallita' }
}
Push-Location -LiteralPath (Join-Path $taskRoot 'motore/video-gfx')
try {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        npm ci
    } elseif (Get-Command pnpm -ErrorAction SilentlyContinue) {
        pnpm install --frozen-lockfile --store-dir (Join-Path $taskCache 'pnpm-store')
    } else {
        throw 'Serve npm o pnpm installato dall’utilizzatore. Nessun tool di sistema verrà scaricato.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Installazione dipendenze Node fallita' }
} finally { Pop-Location }
Write-Host 'Motore pronto. Configura i tuoi percorsi in .env, quindi esegui tools/content_machine.py doctor.'
