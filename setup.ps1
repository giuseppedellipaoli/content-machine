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
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
$taskPython=Join-Path $taskRoot '.venv/Scripts/python.exe'
& $taskPython -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
if ($Transcription) {
    & $taskPython -m pip install -r requirements-transcription.txt
    if ($LASTEXITCODE -ne 0) { throw 'Transcription dependency installation failed' }
}
Push-Location -LiteralPath (Join-Path $taskRoot 'motore/video-gfx')
try {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        npm ci
    } elseif (Get-Command pnpm -ErrorAction SilentlyContinue) {
        pnpm install --frozen-lockfile --store-dir (Join-Path $taskCache 'pnpm-store')
    } else {
        throw 'Install npm or pnpm first. No system tool will be downloaded by this script.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Node dependency installation failed' }
} finally { Pop-Location }
Write-Host 'Engine ready. Configure your own tool paths in .env, then run tools/content_machine.py doctor.'
