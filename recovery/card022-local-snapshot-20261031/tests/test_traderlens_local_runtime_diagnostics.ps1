$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot '..\scripts\traderlens_local_runtime.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $scriptPath,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) {
    throw 'Launcher source did not parse.'
}

$requiredFunctions = @(
    'Test-ServiceReady',
    'Test-ListenerOwnedBy',
    'Get-ListenerIds',
    'Get-HttpStatusCode',
    'Stop-OwnedService',
    'Write-LauncherDiagnostic'
)
$functionAsts = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $requiredFunctions -contains $node.Name
}, $true))
$foundNames = @($functionAsts | ForEach-Object Name)
$missing = @($requiredFunctions | Where-Object { $_ -notin $foundNames })
if ($missing.Count -gt 0) {
    throw "Launcher diagnostic functions are missing: $($missing -join ', ')"
}

foreach ($functionAst in $functionAsts) {
    Invoke-Expression $functionAst.Extent.Text
}

function Assert-Equal($Expected, $Actual, [string]$Name) {
    if ($Expected -ne $Actual) {
        throw "Assertion failed: $Name"
    }
}

function Assert-DoesNotContain([string]$Text, [string]$Value, [string]$Name) {
    if ($Text.Contains($Value)) {
        throw "Unsafe diagnostic output: $Name"
    }
}

$script:MockRootOwned = $true
$script:BackendPort = 8010
$script:FrontendPort = 3000
$script:MockListenerRows = @()
$script:MockListenerQueryFailure = $false
$script:MockListenerQueryErrorId = 'MockListenerQueryFailure'
$script:MockListenerQueryErrorCategory = [System.Management.Automation.ErrorCategory]::ResourceUnavailable
$script:MockProcessInfo = @{}
$script:MockListenerQueryCalls = 0
$script:MockHttpCalls = 0
$script:MockBackendResponse = $null
$script:MockWebResponse = $null
$script:MockWebException = $null

function Test-OwnedRoot($Owned) {
    return [bool]$script:MockRootOwned
}

function Get-NetTCPConnection {
    [CmdletBinding()]
    param([string]$State, [int[]]$LocalPort)
    $script:MockListenerQueryCalls++
    if ($script:MockListenerQueryFailure) {
        $exception = [System.InvalidOperationException]::new('QUERY_MESSAGE_CANARY_DO_NOT_LOG')
        $record = [System.Management.Automation.ErrorRecord]::new(
            $exception,
            $script:MockListenerQueryErrorId,
            $script:MockListenerQueryErrorCategory,
            $null
        )
        $PSCmdlet.WriteError($record)
        return
    }
    return @($script:MockListenerRows)
}

function Get-ProcessInfo([int]$ProcessId) {
    return $script:MockProcessInfo[[int]$ProcessId]
}

function Invoke-RestMethod {
    $script:MockHttpCalls++
    if ($null -ne $script:MockWebException) { throw $script:MockWebException }
    return $script:MockBackendResponse
}

function Invoke-WebRequest {
    $script:MockHttpCalls++
    if ($null -ne $script:MockWebException) { throw $script:MockWebException }
    return $script:MockWebResponse
}

$owned = [pscustomobject]@{ pid = 100; runner = 'simulated-runner.cmd'; startTicks = '0' }

# Empty results from a successful query and a suppressed query error must remain distinguishable.
$script:MockListenerRows = @()
$script:MockListenerQueryFailure = $false
$queryDiagnostic = $null
$listenerIds = @(Get-ListenerIds 8010 ([ref]$queryDiagnostic))
Assert-Equal 0 $listenerIds.Count 'successful empty listener query stays empty'
Assert-Equal $true $queryDiagnostic.passed 'successful listener query is recorded'
Assert-Equal $null $queryDiagnostic.exception_category 'successful query has no exception category'

# The exact no-listener result and other query errors have separate safe classifications.
$script:MockListenerQueryFailure = $true
$script:MockListenerQueryErrorId = 'CmdletizationQuery_NotFound'
$script:MockListenerQueryErrorCategory = [System.Management.Automation.ErrorCategory]::ObjectNotFound
$queryDiagnostic = $null
$listenerIds = @(Get-ListenerIds 8010 ([ref]$queryDiagnostic))
Assert-Equal 0 $listenerIds.Count 'no-match query returns no listener IDs'
Assert-Equal $false $queryDiagnostic.passed 'no-match preserves the existing query gate result'
Assert-Equal 'ObjectNotFound' $queryDiagnostic.error_category 'no-match category is captured as an enum'
Assert-Equal 'NoListenerMatch' $queryDiagnostic.failure_kind 'exact no-match FQID is reduced to a safe classification'

$script:MockListenerQueryErrorId = 'AccessDenied,Get-NetTCPConnection'
$script:MockListenerQueryErrorCategory = [System.Management.Automation.ErrorCategory]::PermissionDenied
$queryDiagnostic = $null
$listenerIds = @(Get-ListenerIds 8010 ([ref]$queryDiagnostic))
Assert-Equal $false $queryDiagnostic.passed 'permission denial remains a query failure'
Assert-Equal 'PermissionDenied' $queryDiagnostic.error_category 'permission category remains distinct'
Assert-Equal 'PermissionDenied' $queryDiagnostic.failure_kind 'permission failure is classified separately'

$script:MockListenerQueryErrorId = 'CimJobException,Get-NetTCPConnection'
$script:MockListenerQueryErrorCategory = [System.Management.Automation.ErrorCategory]::ResourceUnavailable
$queryDiagnostic = $null
$listenerIds = @(Get-ListenerIds 8010 ([ref]$queryDiagnostic))
Assert-Equal $false $queryDiagnostic.passed 'CIM failure remains a query failure'
Assert-Equal 'ResourceUnavailable' $queryDiagnostic.error_category 'CIM category is captured as an enum'
Assert-Equal 'CimFailure' $queryDiagnostic.failure_kind 'CIM failure is classified separately'

$script:MockListenerQueryErrorId = 'QUERY_FQID_CANARY_DO_NOT_LOG'
$script:MockListenerQueryErrorCategory = [System.Management.Automation.ErrorCategory]::ObjectNotFound
$queryDiagnostic = $null
$listenerIds = @(Get-ListenerIds 8010 ([ref]$queryDiagnostic))
Assert-Equal $false $queryDiagnostic.passed 'unrecognized ObjectNotFound remains a query failure'
Assert-Equal 'OtherFailure' $queryDiagnostic.failure_kind 'unrecognized FQID is not treated as expected no-match'

$script:MockListenerQueryErrorId = 'QUERY_FQID_CANARY_DO_NOT_LOG'
$script:MockListenerQueryErrorCategory = [System.Management.Automation.ErrorCategory]::ResourceUnavailable
$queryDiagnostic = $null
$listenerIds = @(Get-ListenerIds 8010 ([ref]$queryDiagnostic))
Assert-Equal 0 $listenerIds.Count 'suppressed query error keeps the existing empty result'
Assert-Equal $false $queryDiagnostic.passed 'suppressed listener query error is recorded'
Assert-Equal 'InvalidOperationException' $queryDiagnostic.exception_category 'query exception type is recorded'
Assert-Equal 'ResourceUnavailable' $queryDiagnostic.error_category 'query error category is recorded safely'
Assert-Equal 'CimFailure' $queryDiagnostic.failure_kind 'query error kind is recorded safely'
Assert-Equal $null $queryDiagnostic.exception_message 'query message is not retained'

$script:MockListenerQueryFailure = $true
$queryDiagnostic = $null
$listenerIds = @(Get-ListenerIds 8010 ([ref]$queryDiagnostic))
Assert-Equal 0 $listenerIds.Count 'suppressed query error keeps the existing empty result'
Assert-Equal $false $queryDiagnostic.passed 'suppressed listener query error is recorded'
Assert-Equal 'InvalidOperationException' $queryDiagnostic.exception_category 'query exception type is recorded'
Assert-Equal $null $queryDiagnostic.exception_message 'query message is not retained'

$script:MockRootOwned = $true
$script:MockListenerRows = @()
$script:MockListenerQueryFailure = $true
$script:MockListenerQueryErrorId = 'QUERY_FQID_CANARY_DO_NOT_LOG'
$script:MockListenerQueryErrorCategory = [System.Management.Automation.ErrorCategory]::ResourceUnavailable
$script:MockProcessInfo = @{}
$diagnostic = $null
$ready = Test-ServiceReady 'backend' $owned ([ref]$diagnostic)
Assert-Equal $false $ready 'listener query failure remains not ready'
Assert-Equal $false $diagnostic.listener_present 'query failure preserves the existing empty listener result'
Assert-Equal $false $diagnostic.listener_query_passed 'readiness diagnostic distinguishes query failure'
Assert-Equal 'InvalidOperationException' $diagnostic.listener_query_exception_category 'readiness diagnostic records query exception type'
Assert-Equal 'ResourceUnavailable' $diagnostic.listener_query_error_category 'readiness captures the safe query error category'
Assert-Equal 'CimFailure' $diagnostic.listener_query_failure_kind 'readiness captures the safe query error kind'
Assert-Equal $null $diagnostic.http_status 'query failure skips HTTP probe'
$listenerQueryFailureDiagnostic = $diagnostic

# A no-match result still fails readiness and never reaches the HTTP probe.
$script:MockListenerQueryErrorId = 'CmdletizationQuery_NotFound'
$script:MockListenerQueryErrorCategory = [System.Management.Automation.ErrorCategory]::ObjectNotFound
$script:MockHttpCalls = 0
$diagnostic = $null
$ready = Test-ServiceReady 'backend' $owned ([ref]$diagnostic)
Assert-Equal $false $ready 'no listener remains not ready'
Assert-Equal $false $diagnostic.listener_query_passed 'no-match does not relax the existing query gate'
Assert-Equal 'ObjectNotFound' $diagnostic.listener_query_error_category 'no-match category survives readiness diagnostic'
Assert-Equal 'NoListenerMatch' $diagnostic.listener_query_failure_kind 'no-match kind survives readiness diagnostic'
Assert-Equal $false $diagnostic.listener_present 'no-match remains absent from the listener gate'
Assert-Equal $null $diagnostic.http_status 'no-match skips the HTTP probe'
Assert-Equal 0 $script:MockHttpCalls 'no-match does not reach the HTTP request'
$listenerQueryNoMatchDiagnostic = $diagnostic

# A failed root ownership check must short-circuit before listener or HTTP checks.
$script:MockRootOwned = $false
$script:MockListenerRows = @()
$script:MockListenerQueryFailure = $false
$script:MockListenerQueryCalls = 0
$script:MockHttpCalls = 0
$diagnostic = $null
$ready = Test-ServiceReady 'backend' $owned ([ref]$diagnostic)
Assert-Equal $false $ready 'root ownership failure remains not ready'
Assert-Equal $false $diagnostic.root_owned 'root failure recorded'
Assert-Equal $null $diagnostic.listener_present 'listener stage not checked after root failure'
Assert-Equal 0 $script:MockListenerQueryCalls 'root failure skips listener query'
Assert-Equal 0 $script:MockHttpCalls 'root failure skips HTTP request'

# Listener ancestry must be reported without relaxing the existing ownership gate.
$script:MockRootOwned = $true
$script:MockListenerRows = @([pscustomobject]@{ OwningProcess = 301 })
$script:MockListenerQueryFailure = $false
$script:MockProcessInfo = @{
    301 = [pscustomobject]@{ ProcessId = 301; ParentProcessId = 0 }
}
$script:MockHttpCalls = 0
$diagnostic = $null
$ready = Test-ServiceReady 'backend' $owned ([ref]$diagnostic)
Assert-Equal $false $ready 'unowned listener remains not ready'
Assert-Equal $true $diagnostic.listener_present 'listener presence recorded'
Assert-Equal $false $diagnostic.listener_owned 'listener ancestry failure recorded'
Assert-Equal $true $diagnostic.listener_query_passed 'listener query success is recorded'
Assert-Equal $null $diagnostic.http_status 'HTTP stage skipped after ancestry failure'
Assert-Equal 0 $script:MockHttpCalls 'unowned listener skips HTTP request'

# Backend health response is reduced to a boolean; response content is never retained.
$script:MockListenerRows = @([pscustomobject]@{ OwningProcess = 301 })
$script:MockListenerQueryFailure = $false
$script:MockProcessInfo = @{
    301 = [pscustomobject]@{ ProcessId = 301; ParentProcessId = 100 }
    100 = [pscustomobject]@{ ProcessId = 100; ParentProcessId = 0 }
}
$script:MockBackendResponse = [pscustomobject]@{
    is_healthy = $false
    is_real_mode = $false
    response_body_canary = 'BODY_CANARY_DO_NOT_LOG'
}
$script:MockWebException = $null
$diagnostic = $null
$ready = Test-ServiceReady 'backend' $owned ([ref]$diagnostic)
Assert-Equal $false $ready 'failed backend health predicate remains not ready'
Assert-Equal $true $diagnostic.root_owned 'backend root ownership recorded'
Assert-Equal $true $diagnostic.listener_owned 'backend listener ownership recorded'
Assert-Equal 200 $diagnostic.http_status 'backend HTTP status recorded'
Assert-Equal $false $diagnostic.probe_passed 'backend health predicate recorded'
Assert-Equal $null $diagnostic.response_body_canary 'backend response body excluded'

# HTTP exceptions may expose status and type only, never their URL, message, or response body.
$script:MockWebException = $null
$script:MockWebResponse = [pscustomobject]@{ StatusCode = 200; Content = 'BODY_CANARY_DO_NOT_LOG' }
$diagnostic = $null
$ready = Test-ServiceReady 'frontend' $owned ([ref]$diagnostic)
Assert-Equal $true $ready 'frontend HTTP 200 remains ready'
Assert-Equal 200 $diagnostic.http_status 'frontend HTTP status recorded'
Assert-Equal $true $diagnostic.probe_passed 'frontend HTTP gate recorded'

$exception = [System.InvalidOperationException]::new('URL_CANARY_DO_NOT_LOG?token=VALUE_CANARY_DO_NOT_LOG')
$exception | Add-Member -NotePropertyName Response -NotePropertyValue ([pscustomobject]@{
    StatusCode = 503
    Content = 'BODY_CANARY_DO_NOT_LOG'
})
$script:MockWebException = $exception
$diagnostic = $null
$ready = Test-ServiceReady 'frontend' $owned ([ref]$diagnostic)
Assert-Equal $false $ready 'HTTP exception remains not ready'
Assert-Equal 503 $diagnostic.http_status 'HTTP status extracted without body'
Assert-Equal 'InvalidOperationException' $diagnostic.exception_category 'exception type recorded'

$tempFile = [System.IO.Path]::GetTempFileName()
try {
    $diagnostic.cleanup_status = 'stopped_confirmed'
    $diagnostic | Add-Member -NotePropertyName exception_message -NotePropertyValue 'MESSAGE_CANARY_DO_NOT_LOG'
    $diagnostic | Add-Member -NotePropertyName url -NotePropertyValue 'https://example.invalid/?key=URL_CANARY_DO_NOT_LOG'
    $diagnostic | Add-Member -NotePropertyName response_body -NotePropertyValue 'BODY_CANARY_DO_NOT_LOG'
    $display = (& { Write-LauncherDiagnostic -Path $tempFile -Entry $diagnostic } 6>&1 | Out-String)
    $stored = Get-Content -LiteralPath $tempFile -Raw
    foreach ($canary in @('URL_CANARY_DO_NOT_LOG', 'VALUE_CANARY_DO_NOT_LOG', 'BODY_CANARY_DO_NOT_LOG', 'MESSAGE_CANARY_DO_NOT_LOG')) {
        Assert-DoesNotContain $stored $canary 'persisted diagnostic is allowlisted'
        Assert-DoesNotContain $display $canary 'console diagnostic is allowlisted'
    }
    $record = $stored.Trim() | ConvertFrom-Json
    Assert-Equal 'frontend' $record.service 'service name is recorded'
    Assert-Equal 3000 $record.port 'service port is recorded'
    Assert-Equal $true $record.listener_query_passed 'listener query status is persisted'
    Assert-Equal 503 $record.http_status 'safe HTTP status is persisted'
    Assert-Equal 'InvalidOperationException' $record.exception_category 'safe exception category is persisted'
    Assert-Equal $true $record.listener_query_passed 'successful listener query result is persisted'
    Assert-Equal $null $record.listener_query_exception_category 'successful query stores no exception category'
    Assert-Equal 'stopped_confirmed' $record.cleanup_status 'cleanup outcome is persisted'
    $expectedKeys = @('timestamp_utc', 'service', 'port', 'root_owned', 'listener_query_passed', 'listener_query_exception_category', 'listener_query_error_category', 'listener_query_failure_kind', 'listener_present', 'listener_owned', 'http_status', 'probe_passed', 'exception_category', 'ready', 'cleanup_status')
    $actualKeys = @($record.PSObject.Properties.Name)
    if (@(Compare-Object -ReferenceObject $expectedKeys -DifferenceObject $actualKeys).Count -gt 0) {
        throw 'Diagnostic record contains fields outside the safe allowlist.'
    }

    $queryFailureTempFile = [System.IO.Path]::GetTempFileName()
    try {
        $listenerQueryFailureDiagnostic.cleanup_status = 'already_exited'
        $queryFailureDisplay = (& { Write-LauncherDiagnostic -Path $queryFailureTempFile -Entry $listenerQueryFailureDiagnostic } 6>&1 | Out-String)
        $queryFailureStored = Get-Content -LiteralPath $queryFailureTempFile -Raw
        Assert-DoesNotContain $queryFailureStored 'QUERY_MESSAGE_CANARY_DO_NOT_LOG' 'query error message is absent from persisted record'
        Assert-DoesNotContain $queryFailureDisplay 'QUERY_MESSAGE_CANARY_DO_NOT_LOG' 'query error message is absent from console output'
        $queryFailureRecord = $queryFailureStored.Trim() | ConvertFrom-Json
        Assert-Equal $false $queryFailureRecord.listener_query_passed 'query failure is persisted'
        Assert-Equal 'InvalidOperationException' $queryFailureRecord.listener_query_exception_category 'query exception type is persisted'
        Assert-Equal 'ResourceUnavailable' $queryFailureRecord.listener_query_error_category 'query error category is persisted safely'
        Assert-Equal 'CimFailure' $queryFailureRecord.listener_query_failure_kind 'query error kind is persisted safely'
        Assert-Equal $null $queryFailureRecord.http_status 'query failure record has no HTTP status'
    } finally {
        Remove-Item -LiteralPath $queryFailureTempFile -Force
    }

    $noMatchTempFile = [System.IO.Path]::GetTempFileName()
    try {
        $listenerQueryNoMatchDiagnostic.cleanup_status = 'already_exited'
        $noMatchDisplay = (& { Write-LauncherDiagnostic -Path $noMatchTempFile -Entry $listenerQueryNoMatchDiagnostic } 6>&1 | Out-String)
        $noMatchStored = Get-Content -LiteralPath $noMatchTempFile -Raw
        Assert-DoesNotContain $noMatchStored 'CmdletizationQuery_NotFound,Get-NetTCPConnection' 'raw no-match FQID is not persisted'
        Assert-DoesNotContain $noMatchDisplay 'CmdletizationQuery_NotFound,Get-NetTCPConnection' 'raw no-match FQID is not displayed'
        Assert-DoesNotContain $noMatchStored 'QUERY_FQID_CANARY_DO_NOT_LOG' 'arbitrary FQID is not persisted'
        Assert-DoesNotContain $noMatchDisplay 'QUERY_FQID_CANARY_DO_NOT_LOG' 'arbitrary FQID is not displayed'
        $noMatchRecord = $noMatchStored.Trim() | ConvertFrom-Json
        Assert-Equal 'ObjectNotFound' $noMatchRecord.listener_query_error_category 'no-match enum is persisted'
        Assert-Equal 'NoListenerMatch' $noMatchRecord.listener_query_failure_kind 'no-match kind is persisted'
    } finally {
        Remove-Item -LiteralPath $noMatchTempFile -Force
    }

    $missingDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("TraderLens-missing-{0}" -f [Guid]::NewGuid().ToString('N'))
    $missingPath = Join-Path $missingDirectory 'diagnostics.jsonl'
    $failedWriteDisplay = & {
        $writeResult = Write-LauncherDiagnostic -Path $missingPath -Entry $diagnostic
        Write-Output ("WRITE_RESULT=" + $writeResult)
    } 6>&1 | Out-String
    if ($failedWriteDisplay -notmatch 'WRITE_RESULT=False' -or $failedWriteDisplay -notmatch '"service":"frontend"') {
        throw 'Diagnostic record was not displayed when persistence failed.'
    }
} finally {
    Remove-Item -LiteralPath $tempFile -Force
}

# Cleanup outcome can be tested without invoking taskkill or touching a real process.
$script:MockRootOwned = $false
$script:MockProcessInfo = @{}
$outcome = $null
$stopped = Stop-OwnedService 'backend' $owned -Quiet -Outcome ([ref]$outcome)
Assert-Equal $true $stopped 'missing process remains a successful no-op cleanup'
Assert-Equal 'already_exited' $outcome 'cleanup outcome recorded'

Write-Output 'PASS: 10 isolated launcher diagnostic assertions'
Write-Output ("SAFE_SAMPLE=" + ($record | ConvertTo-Json -Compress))
Write-Output ("QUERY_FAILURE_SAMPLE=" + ($queryFailureRecord | ConvertTo-Json -Compress))
