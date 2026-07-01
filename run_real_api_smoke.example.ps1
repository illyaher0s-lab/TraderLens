# Real API smoke test runner template.
# Copy to a local untracked script if needed, or set these variables in your shell.
# Do not write real API keys or tokens into this file.

$requiredVars = @(
    "TUSHARE_TOKEN",
    "RESEARCH_LLM_API_KEY"
)

$env:RUN_REAL_API_SMOKE = "1"

if (-not $env:TUSHARE_API_URL) {
    Write-Host "TUSHARE_API_URL is optional and not set."
}

if (-not $env:RESEARCH_LLM_BASE_URL) {
    $env:RESEARCH_LLM_BASE_URL = "https://cc-vibe.com"
}

if (-not $env:RESEARCH_LLM_MODEL) {
    $env:RESEARCH_LLM_MODEL = "claude-sonnet-4-6"
}

foreach ($var in $requiredVars) {
    if (-not [Environment]::GetEnvironmentVariable($var)) {
        throw "$var is required. Set it in your local shell; do not commit it."
    }
}

$env:HTTP_PROXY = $null
$env:HTTPS_PROXY = $null
$env:http_proxy = $null
$env:https_proxy = $null
$env:ALL_PROXY = $null
$env:all_proxy = $null

Write-Host "Running real API smoke tests with local environment variables."
Write-Host "TUSHARE_API_URL=$env:TUSHARE_API_URL"
Write-Host "RESEARCH_LLM_BASE_URL=$env:RESEARCH_LLM_BASE_URL"
Write-Host "RESEARCH_LLM_MODEL=$env:RESEARCH_LLM_MODEL"

& .venv\Scripts\python.exe -m pytest tests/test_v1_real_api_smoke.py -v -s
