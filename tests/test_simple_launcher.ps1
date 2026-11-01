$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcherPath = Join-Path $PSScriptRoot '..\scripts\start-traderlens.ps1'
if (-not (Test-Path -LiteralPath $launcherPath)) {
    throw 'A simple TraderLens launcher is required.'
}
$launcherBytes = [System.IO.File]::ReadAllBytes($launcherPath)
if (
    $launcherBytes.Length -lt 3 -or
    $launcherBytes[0] -ne 0xEF -or
    $launcherBytes[1] -ne 0xBB -or
    $launcherBytes[2] -ne 0xBF
) {
    throw 'The launcher must use UTF-8 with BOM for Windows PowerShell 5.1.'
}

$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $launcherPath, [ref]$tokens, [ref]$errors
)
if ($errors.Count -gt 0) { throw 'Launcher must parse.' }
$names = @('Assert-PortsAvailable', 'Wait-ForWebsite', 'Start-TraderLens')
$functions = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $names -contains $node.Name
}, $true))
foreach ($name in $names) {
    if ($name -notin @($functions | ForEach-Object Name)) { throw "Missing launcher function: $name" }
}
foreach ($function in $functions) { Invoke-Expression $function.Extent.Text }

$startPath = Join-Path $projectRoot 'start.bat'
$stopPath = Join-Path $projectRoot 'stop.bat'
$startText = Get-Content -LiteralPath $startPath -Raw
$stopText = Get-Content -LiteralPath $stopPath -Raw
if ($startText -notmatch 'scripts\\start-traderlens\.ps1' -or $startText -match 'traderlens_local_runtime\.ps1') {
    throw 'start.bat must call the simple launcher directly.'
}
if ($stopText -notmatch 'Ctrl\+C' -or $stopText -notmatch 'does not terminate processes' -or $stopText -match 'traderlens_local_runtime\.ps1') {
    throw 'stop.bat must give honest visible-window instructions without managing unrelated processes.'
}
if (Test-Path -LiteralPath (Join-Path $projectRoot 'scripts\traderlens_local_runtime.ps1')) {
    throw 'The superseded process-manager implementation should be removed after its callers are migrated.'
}

$launcherText = Get-Content -LiteralPath $launcherPath -Raw
if ($launcherText -match '(?im)\bRead-Host\b' -or $launcherText -match '(?im)Get-Content[^\r\n]*\.env') {
    throw 'The launcher must use existing process environment and must not prompt for or read secret files.'
}
if ($launcherText -match '(?im)\b(?:Stop-Process|taskkill)\b') {
    throw 'The simple launcher must never terminate an existing process.'
}

$env:RESEARCH_LLM_API_KEY = 'CARD022_FAKE_TEST_ONLY'
$env:TUSHARE_TOKEN = 'CARD022_FAKE_TEST_ONLY'
$script:MockListeners = @()
$script:MockQueryFailure = $null
$script:Calls = @()
$script:BackendReady = $true
$script:FrontendReady = $true
function Get-NetTCPConnection {
    [CmdletBinding()]
    param([int]$LocalPort, [string]$State)
    if ($script:MockQueryFailure) {
        switch ($script:MockQueryFailure) {
            'PermissionDenied' {
                $exception = [System.UnauthorizedAccessException]::new('access denied')
                $record = [System.Management.Automation.ErrorRecord]::new(
                    $exception,
                    'AccessDenied',
                    [System.Management.Automation.ErrorCategory]::PermissionDenied,
                    $LocalPort
                )
            }
            'ObjectNotFoundOtherId' {
                $exception = [System.InvalidOperationException]::new('unexpected object-not-found')
                $record = [System.Management.Automation.ErrorRecord]::new(
                    $exception,
                    'UnexpectedQueryShape',
                    [System.Management.Automation.ErrorCategory]::ObjectNotFound,
                    $LocalPort
                )
            }
            default {
                $exception = [System.InvalidOperationException]::new('unexpected query failure')
                $record = [System.Management.Automation.ErrorRecord]::new(
                    $exception,
                    'UnexpectedQueryFailure',
                    [System.Management.Automation.ErrorCategory]::NotSpecified,
                    $LocalPort
                )
            }
        }
        $PSCmdlet.ThrowTerminatingError($record)
    }

    $matches = @($script:MockListeners | Where-Object { $_.LocalPort -eq $LocalPort })
    if ($matches.Count -eq 0) {
        $exception = [System.InvalidOperationException]::new('no listening sockets matched')
        $record = [System.Management.Automation.ErrorRecord]::new(
            $exception,
            'CmdletizationQuery_NotFound',
            [System.Management.Automation.ErrorCategory]::ObjectNotFound,
            $LocalPort
        )
        $PSCmdlet.ThrowTerminatingError($record)
    }
    return $matches
}
function Start-Process {
    [CmdletBinding()]
    param([string]$FilePath, [object[]]$ArgumentList, [string]$WorkingDirectory, [string]$WindowStyle)
    $script:Calls += [pscustomobject]@{
        FilePath = $FilePath
        ArgumentList = $ArgumentList
        WorkingDirectory = $WorkingDirectory
        WindowStyle = $WindowStyle
    }
}
function Invoke-RestMethod {
    [CmdletBinding()]
    param([string]$Uri, [int]$TimeoutSec)
    if (-not $script:BackendReady) { throw 'backend not ready' }
    return [pscustomobject]@{ is_healthy = $true; is_real_mode = $true }
}
function Invoke-WebRequest {
    [CmdletBinding()]
    param([string]$Uri, [int]$TimeoutSec, [switch]$UseBasicParsing)
    if (-not $script:FrontendReady) { throw 'frontend not ready' }
    return [pscustomobject]@{ StatusCode = 200 }
}
function Start-Sleep { param([int]$Seconds) }

$mockNoListenerError = $null
try { Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction Stop } catch { $mockNoListenerError = $_ }
if (
    $null -eq $mockNoListenerError -or
    $mockNoListenerError.CategoryInfo.Category -ne [System.Management.Automation.ErrorCategory]::ObjectNotFound -or
    $mockNoListenerError.FullyQualifiedErrorId -cne 'CmdletizationQuery_NotFound,Get-NetTCPConnection'
) {
    throw 'The empty-port mock must match the Windows Get-NetTCPConnection error category and ID.'
}

if (-not (Wait-ForWebsite -Attempts 1 -DelaySeconds 0)) { throw 'Ready services should be accepted.' }
$script:BackendReady = $false
if (Wait-ForWebsite -Attempts 1 -DelaySeconds 0) { throw 'An unavailable backend must not be reported ready.' }
$script:BackendReady = $true
$script:FrontendReady = $false
if (Wait-ForWebsite -Attempts 1 -DelaySeconds 0) { throw 'An unavailable frontend must not be reported ready.' }
$script:FrontendReady = $true

$env:RESEARCH_LLM_API_KEY = ''
$blockedMessage = ''
try { Start-TraderLens -ProjectRoot $projectRoot } catch { $blockedMessage = $_.Exception.Message }
if ($blockedMessage -notmatch 'RESEARCH_LLM_API_KEY' -or $script:Calls.Count -ne 0) {
    throw 'Missing LLM configuration must fail clearly before launching a process.'
}
$env:RESEARCH_LLM_API_KEY = 'CARD022_FAKE_TEST_ONLY'
$env:TUSHARE_TOKEN = ''
$blockedMessage = ''
try { Start-TraderLens -ProjectRoot $projectRoot } catch { $blockedMessage = $_.Exception.Message }
if ($blockedMessage -notmatch 'TUSHARE_TOKEN' -or $script:Calls.Count -ne 0) {
    throw 'Missing Tushare configuration must fail clearly before launching a process.'
}
$env:TUSHARE_TOKEN = 'CARD022_FAKE_TEST_ONLY'

$script:MockListeners = @([pscustomobject]@{ LocalPort = 3000 })
$blocked = $false
try { Start-TraderLens -ProjectRoot $projectRoot } catch { $blocked = $true }
if (-not $blocked -or $script:Calls.Count -ne 0) { throw 'An occupied port must stop launch without starting anything.' }

$script:MockListeners = @([pscustomobject]@{ LocalPort = 8010 })
$blocked = $false
try { Start-TraderLens -ProjectRoot $projectRoot } catch { $blocked = $true }
if (-not $blocked -or $script:Calls.Count -ne 0) { throw 'A backend port conflict must stop launch without starting anything.' }

$script:MockListeners = @()
$script:MockQueryFailure = 'PermissionDenied'
$blocked = $false
try { Start-TraderLens -ProjectRoot $projectRoot } catch { $blocked = $true }
if (-not $blocked -or $script:Calls.Count -ne 0) { throw 'PermissionDenied must stop launch without starting anything.' }

$script:MockQueryFailure = 'ObjectNotFoundOtherId'
$blocked = $false
try { Start-TraderLens -ProjectRoot $projectRoot } catch { $blocked = $true }
if (-not $blocked -or $script:Calls.Count -ne 0) { throw 'A different ObjectNotFound error must stop launch.' }

$script:MockQueryFailure = $null
Start-TraderLens -ProjectRoot $projectRoot
if ($script:Calls.Count -ne 3) { throw 'Expected backend window, frontend window, and browser.' }
if ($script:Calls[0].WindowStyle -ne 'Normal' -or $script:Calls[1].WindowStyle -ne 'Normal') {
    throw 'Server windows must remain visible and interactive.'
}
if ($script:Calls[2].FilePath -ne 'http://localhost:3000/') { throw 'Expected the local homepage.' }
$backendArguments = $script:Calls[0].ArgumentList -join ' '
$frontendArguments = $script:Calls[1].ArgumentList -join ' '
if ($script:Calls[0].WorkingDirectory -ne $projectRoot -or $backendArguments -notmatch 'uvicorn backend\.app\.main:app.*127\.0\.0\.1.*8010') {
    throw 'The backend must start from this checkout on loopback port 8010.'
}
if ($script:Calls[1].WorkingDirectory -ne $projectRoot -or $frontendArguments -notmatch 'npm\.cmd.*run dev.*127\.0\.0\.1.*3000') {
    throw 'The frontend must start from this checkout on loopback port 3000.'
}
foreach ($call in $script:Calls) {
    if (($call.ArgumentList -join ' ').Contains('CARD022_FAKE_TEST_ONLY')) {
        throw 'Credential values must be inherited through the environment, not exposed in process arguments.'
    }
}
Write-Output 'Simple launcher checks passed.'
