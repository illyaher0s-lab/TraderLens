param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Start', 'Stop')]
    [string]$Action,
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
$BackendPort = 8010
$FrontendPort = 3000
$BackendHealthUrl = "http://127.0.0.1:$BackendPort/api/research/service-health"
$HomeUrl = "http://localhost:$FrontendPort/"
$HomeReadyUrl = "http://127.0.0.1:$FrontendPort/"
$RootHash = [System.Security.Cryptography.SHA256]::Create()
$RootHashText = [BitConverter]::ToString($RootHash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Root.ToLowerInvariant()))).Replace('-', '').Substring(0, 16)
$StateDirectory = Join-Path $env:TEMP "TraderLens-local-$RootHashText"
$StatePath = Join-Path $StateDirectory 'launcher-state.json'
$ComSpecPath = [System.IO.Path]::GetFullPath($env:ComSpec)

function New-EmptyState {
    return [pscustomobject]@{
        schemaVersion = 1
        projectRoot = $Root
        backend = $null
        frontend = $null
    }
}

function Read-State {
    if (-not (Test-Path -LiteralPath $StatePath)) { return (New-EmptyState) }
    $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    if ($state.schemaVersion -ne 1 -or [System.IO.Path]::GetFullPath([string]$state.projectRoot).TrimEnd('\') -ine $Root) {
        throw '启动记录与当前项目不匹配；未终止任何进程。'
    }
    return $state
}

function Save-State($State) {
    New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
    $tempPath = "$StatePath.tmp"
    $State | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $tempPath -Encoding UTF8
    Move-Item -LiteralPath $tempPath -Destination $StatePath -Force
}

function Get-ProcessInfo([int]$ProcessId) {
    return Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Test-OwnedRoot($Owned) {
    if ($null -eq $Owned -or -not $Owned.pid -or -not $Owned.runner) { return $false }
    $info = Get-ProcessInfo ([int]$Owned.pid)
    if ($null -eq $info -or [string]::IsNullOrWhiteSpace([string]$info.CommandLine)) { return $false }
    if ([System.IO.Path]::GetFullPath([string]$info.ExecutablePath) -ine $ComSpecPath) { return $false }
    if ([string]$info.CommandLine -notlike "*$([string]$Owned.runner)*") { return $false }
    try {
        $process = Get-Process -Id ([int]$Owned.pid) -ErrorAction Stop
        $difference = [Math]::Abs([double]$process.StartTime.ToUniversalTime().Ticks - [double]$Owned.startTicks)
        return ($difference -lt 20000000)
    } catch {
        return $false
    }
}

function Test-ListenerOwnedBy {
    param([int]$Port, $Owned, [ref]$Ownership)

    $queryDiagnostic = $null
    $listenerIds = @(Get-ListenerIds $Port ([ref]$queryDiagnostic))
    $listenerOwned = $false
    foreach ($listenerId in $listenerIds) {
        $current = Get-ProcessInfo ([int]$listenerId)
        for ($depth = 0; $depth -lt 24 -and $null -ne $current; $depth++) {
            if ([int]$current.ProcessId -eq [int]$Owned.pid) {
                $listenerOwned = $true
                break
            }
            $parentId = [int]$current.ParentProcessId
            if ($parentId -le 0 -or $parentId -eq [int]$current.ProcessId) { break }
            $current = Get-ProcessInfo $parentId
        }
        if ($listenerOwned) { break }
    }

    if ($PSBoundParameters.ContainsKey('Ownership')) {
        $null = $Ownership.Value = [pscustomobject]@{
            query_passed = $queryDiagnostic.passed
            query_exception_category = $queryDiagnostic.exception_category
            query_error_category = $queryDiagnostic.error_category
            query_failure_kind = $queryDiagnostic.failure_kind
            present = ($listenerIds.Count -gt 0)
            owned = [bool]$listenerOwned
        }
    }
    return [bool]$listenerOwned
}

function Get-ListenerIds {
    param([int]$Port, [ref]$QueryDiagnostic)

    $queryErrors = @()
    $listenerIds = @(
        Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue -ErrorVariable queryErrors |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { [int]$_ }
    )

    $queryPassed = ($queryErrors.Count -eq 0)
    $exceptionCategory = $null
    $errorCategory = $null
    $failureKind = $null
    if (-not $queryPassed) {
        $queryError = $queryErrors[0]
        $exception = $queryError.Exception
        if ($null -ne $exception -and $exception -is [System.Management.Automation.RuntimeException] -and $null -ne $exception.InnerException) {
            $exception = $exception.InnerException
        }
        if ($null -ne $exception -and $exception.GetType().Name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
            $exceptionCategory = $exception.GetType().Name
        } else {
            $exceptionCategory = 'OtherException'
        }

        switch -CaseSensitive ([string]$queryError.CategoryInfo.Category) {
            'ObjectNotFound' { $errorCategory = 'ObjectNotFound' }
            'PermissionDenied' { $errorCategory = 'PermissionDenied' }
            'ResourceUnavailable' { $errorCategory = 'ResourceUnavailable' }
            default { $errorCategory = 'Other' }
        }

        if (
            $queryErrors.Count -eq 1 -and
            $listenerIds.Count -eq 0 -and
            $errorCategory -eq 'ObjectNotFound' -and
            [string]$queryError.FullyQualifiedErrorId -ceq 'CmdletizationQuery_NotFound,Get-NetTCPConnection'
        ) {
            $failureKind = 'NoListenerMatch'
        } elseif ($errorCategory -eq 'PermissionDenied') {
            $failureKind = 'PermissionDenied'
        } elseif ($errorCategory -eq 'ResourceUnavailable' -or ($null -ne $exception -and $exception.GetType().Name -eq 'CimJobException')) {
            $failureKind = 'CimFailure'
        } else {
            $failureKind = 'OtherFailure'
        }
    }

    if ($PSBoundParameters.ContainsKey('QueryDiagnostic')) {
        $null = $QueryDiagnostic.Value = [pscustomobject]@{
            passed = [bool]$queryPassed
            exception_category = $exceptionCategory
            error_category = $errorCategory
            failure_kind = $failureKind
        }
    }
    return $listenerIds
}

function Get-HttpStatusCode($ErrorRecord) {
    try {
        $exception = $ErrorRecord.Exception
        while ($null -ne $exception) {
            $responseProperty = $exception.PSObject.Properties['Response']
            if ($null -ne $responseProperty -and $null -ne $responseProperty.Value) {
                $statusProperty = $responseProperty.Value.PSObject.Properties['StatusCode']
                if ($null -ne $statusProperty -and $null -ne $statusProperty.Value) {
                    try {
                        $statusCode = [int]$statusProperty.Value
                        if ($statusCode -ge 100 -and $statusCode -le 599) { return $statusCode }
                    } catch { }
                }
            }
            $exception = $exception.InnerException
        }
    } catch { }
    return $null
}

function Test-ServiceReady {
    param([string]$Name, $Owned, [ref]$Diagnostic)

    $port = if ($Name -eq 'backend') { $BackendPort } else { $FrontendPort }
    $details = [pscustomobject]@{
        service = $Name
        port = $port
        root_owned = $false
        listener_query_passed = $null
        listener_query_exception_category = $null
        listener_query_error_category = $null
        listener_query_failure_kind = $null
        listener_present = $null
        listener_owned = $null
        http_status = $null
        probe_passed = $null
        exception_category = $null
        ready = $false
        cleanup_status = $null
    }

    if (-not (Test-OwnedRoot $Owned)) {
        if ($null -ne $Diagnostic) { $null = $Diagnostic.Value = $details }
        return $false
    }
    $details.root_owned = $true

    $ownership = $null
    $listenerOwned = Test-ListenerOwnedBy $port $Owned ([ref]$ownership)
    $details.listener_query_passed = $ownership.query_passed
    $details.listener_query_exception_category = $ownership.query_exception_category
    $details.listener_query_error_category = $ownership.query_error_category
    $details.listener_query_failure_kind = $ownership.query_failure_kind
    $details.listener_present = [bool]$ownership.present
    $details.listener_owned = [bool]$ownership.owned
    if (-not $listenerOwned) {
        if ($null -ne $Diagnostic) { $null = $Diagnostic.Value = $details }
        return $false
    }

    try {
        if ($Name -eq 'backend') {
            $health = Invoke-RestMethod -Uri $BackendHealthUrl -TimeoutSec 2
            $details.http_status = 200
            $details.probe_passed = [bool]($health.is_healthy -eq $true -and $health.is_real_mode -eq $true)
        } else {
            $response = Invoke-WebRequest -Uri $HomeReadyUrl -UseBasicParsing -TimeoutSec 2
            $details.http_status = [int]$response.StatusCode
            $details.probe_passed = [bool]($response.StatusCode -eq 200)
        }
    } catch {
        $details.http_status = Get-HttpStatusCode $_
        $exception = $_.Exception
        if ($null -ne $exception -and $exception -is [System.Management.Automation.RuntimeException] -and $null -ne $exception.InnerException) {
            $exception = $exception.InnerException
        }
        if ($null -ne $exception -and $exception.GetType().Name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
            $details.exception_category = $exception.GetType().Name
        } else {
            $details.exception_category = 'OtherException'
        }
        $details.probe_passed = $false
    }

    $details.ready = ($details.probe_passed -eq $true)
    if ($null -ne $Diagnostic) { $null = $Diagnostic.Value = $details }
    return [bool]$details.ready
}

function Set-RealEnvironment {
    $envPath = Join-Path $Root '.env.local'
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                $name = $matches[1]
                $value = $matches[2]
                if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[$value.Length - 1] -eq '"') -or ($value[0] -eq "'" -and $value[$value.Length - 1] -eq "'"))) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
                [Environment]::SetEnvironmentVariable($name, $value, 'Process')
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($env:RESEARCH_LLM_API_KEY)) { throw '真实研究配置缺少 RESEARCH_LLM_API_KEY。' }
    if ([string]::IsNullOrWhiteSpace($env:TUSHARE_TOKEN)) { throw '真实研究配置缺少 TUSHARE_TOKEN。' }
    $env:RESEARCH_CONVERSATION_MODE = 'real'
    $env:SERENITY_EXECUTION_MODE = 'two_phase'
    $env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:$BackendPort"
    $env:BACKEND_PORT = [string]$BackendPort
    if ([string]::IsNullOrWhiteSpace($env:TUSHARE_API_URL)) { $env:TUSHARE_API_URL = 'http://8.163.90.143:8686/' }
    foreach ($name in @('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy')) {
        [Environment]::SetEnvironmentVariable($name, '', 'Process')
    }
}

function Start-OwnedService([string]$Name, $State) {
    $runId = [Guid]::NewGuid().ToString('N')
    $runnerPath = Join-Path $StateDirectory "$Name-$runId.cmd"
    $stdoutPath = Join-Path $StateDirectory "$Name-$runId.out.log"
    $stderrPath = Join-Path $StateDirectory "$Name-$runId.err.log"
    if ($Name -eq 'backend') {
        $pythonPath = Join-Path $Root '.venv\Scripts\python.exe'
        $body = "@echo off`r`ncd /d `"$Root`"`r`n`"$pythonPath`" -m uvicorn backend.app.main:app --app-dir `"$Root`" --host 127.0.0.1 --port $BackendPort`r`n"
    } else {
        $npmCommand = (Get-Command 'npm.cmd' -ErrorAction Stop).Source
        $body = "@echo off`r`ncd /d `"$Root`"`r`ncall `"$npmCommand`" run dev -- --hostname 127.0.0.1 --port $FrontendPort`r`n"
    }
    [System.IO.File]::WriteAllText($runnerPath, $body, [System.Text.Encoding]::ASCII)
    $process = Start-Process -FilePath $ComSpecPath `
        -ArgumentList @('/d', '/c', "call `"$runnerPath`"") `
        -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    Start-Sleep -Milliseconds 250
    $process.Refresh()
    if ($process.HasExited) { throw "$Name 启动命令已退出；日志位于 $stdoutPath" }
    $entry = [pscustomobject]@{
        pid = $process.Id
        startTicks = [string]$process.StartTime.ToUniversalTime().Ticks
        runner = $runnerPath
        stdout = $stdoutPath
        stderr = $stderrPath
    }
    $State.$Name = $entry
    Save-State $State
    return $entry
}

function Stop-OwnedService {
    param([string]$Name, $Owned, [switch]$Quiet, [ref]$Outcome)

    if ($null -eq $Owned) {
        if ($PSBoundParameters.ContainsKey('Outcome')) { $null = $Outcome.Value = 'no_owner_record' }
        return $true
    }
    if (-not (Test-OwnedRoot $Owned)) {
        if ($null -ne (Get-ProcessInfo ([int]$Owned.pid))) {
            if ($PSBoundParameters.ContainsKey('Outcome')) { $null = $Outcome.Value = 'ownership_mismatch_skipped' }
            if (-not $Quiet) { Write-Host "$Name 的进程身份与启动记录不符，已跳过，未终止。" }
        } elseif ($PSBoundParameters.ContainsKey('Outcome')) {
            $null = $Outcome.Value = 'already_exited'
        }
        return $true
    }
    $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
    & $taskkill /F /T /PID ([string]$Owned.pid) 2>$null | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(8)
    do {
        if ($null -eq (Get-ProcessInfo ([int]$Owned.pid))) {
            foreach ($path in @($Owned.runner)) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue } }
            if ($PSBoundParameters.ContainsKey('Outcome')) { $null = $Outcome.Value = 'stopped_confirmed' }
            if (-not $Quiet) { Write-Host "$Name 已停止。" }
            return $true
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($PSBoundParameters.ContainsKey('Outcome')) { $null = $Outcome.Value = 'stop_unconfirmed' }
    if (-not $Quiet) { Write-Host "$Name 未能确认停止；保留启动记录以便重试。" }
    return $false
}

function Write-LauncherDiagnostic([string]$Path, $Entry) {
    $service = if ($Entry.service -in @('backend', 'frontend')) { [string]$Entry.service } else { 'unknown' }
    $cleanupStatuses = @('not_started_this_call', 'no_owner_record', 'already_exited', 'ownership_mismatch_skipped', 'stopped_confirmed', 'stop_unconfirmed')
    $cleanupStatus = if ($Entry.cleanup_status -in $cleanupStatuses) { [string]$Entry.cleanup_status } else { 'unknown' }

    $rootOwned = $null
    if ($null -ne $Entry.root_owned) { $rootOwned = [bool]$Entry.root_owned }
    $listenerPresent = $null
    if ($null -ne $Entry.listener_present) { $listenerPresent = [bool]$Entry.listener_present }
    $listenerOwned = $null
    if ($null -ne $Entry.listener_owned) { $listenerOwned = [bool]$Entry.listener_owned }
    $listenerQueryPassed = $null
    if ($null -ne $Entry.listener_query_passed) { $listenerQueryPassed = [bool]$Entry.listener_query_passed }
    $probePassed = $null
    if ($null -ne $Entry.probe_passed) { $probePassed = [bool]$Entry.probe_passed }

    $httpStatus = $null
    if ($null -ne $Entry.http_status) {
        try {
            $candidateStatus = [int]$Entry.http_status
            if ($candidateStatus -ge 100 -and $candidateStatus -le 599) { $httpStatus = $candidateStatus }
        } catch { }
    }

    $port = $null
    if ($null -ne $Entry.port) {
        try {
            $candidatePort = [int]$Entry.port
            if ($candidatePort -ge 1 -and $candidatePort -le 65535) { $port = $candidatePort }
        } catch { }
    }

    $exceptionCategory = $null
    if ($Entry.exception_category -is [string] -and $Entry.exception_category -match '^[A-Za-z_][A-Za-z0-9_]*$') {
        $exceptionCategory = [string]$Entry.exception_category
    }
    $listenerQueryExceptionCategory = $null
    if ($Entry.listener_query_exception_category -is [string] -and $Entry.listener_query_exception_category -match '^[A-Za-z_][A-Za-z0-9_]*$') {
        $listenerQueryExceptionCategory = [string]$Entry.listener_query_exception_category
    }
    $listenerQueryErrorCategory = $null
    if ($null -ne $Entry.listener_query_error_category) {
        $listenerQueryErrorCategory = if ($Entry.listener_query_error_category -in @('ObjectNotFound', 'PermissionDenied', 'ResourceUnavailable')) {
            [string]$Entry.listener_query_error_category
        } else {
            'Other'
        }
    }
    $listenerQueryFailureKind = $null
    if ($null -ne $Entry.listener_query_failure_kind) {
        $listenerQueryFailureKind = if ($Entry.listener_query_failure_kind -in @('NoListenerMatch', 'PermissionDenied', 'CimFailure', 'OtherFailure')) {
            [string]$Entry.listener_query_failure_kind
        } else {
            'OtherFailure'
        }
    }

    $record = [pscustomobject][ordered]@{
        timestamp_utc = [DateTime]::UtcNow.ToString('o')
        service = $service
        port = $port
        root_owned = $rootOwned
        listener_query_passed = $listenerQueryPassed
        listener_query_exception_category = $listenerQueryExceptionCategory
        listener_query_error_category = $listenerQueryErrorCategory
        listener_query_failure_kind = $listenerQueryFailureKind
        listener_present = $listenerPresent
        listener_owned = $listenerOwned
        http_status = $httpStatus
        probe_passed = $probePassed
        exception_category = $exceptionCategory
        ready = [bool]$Entry.ready
        cleanup_status = $cleanupStatus
    }

    try {
        $line = $record | ConvertTo-Json -Compress
    } catch {
        $category = $_.Exception.GetType().Name
        if ($category -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { $category = 'OtherException' }
        Write-Host "启动诊断序列化失败（异常类型=$category）。" -ForegroundColor Yellow
        return $false
    }

    Write-Host "启动诊断：$line"
    try {
        Add-Content -LiteralPath $Path -Value $line -Encoding UTF8
        return $true
    } catch {
        $category = $_.Exception.GetType().Name
        if ($category -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { $category = 'OtherException' }
        Write-Host "启动诊断记录写入失败（异常类型=$category）。" -ForegroundColor Yellow
        return $false
    }
}

function Invoke-Stop($State) {
    $allStopped = $true
    foreach ($name in @('frontend', 'backend')) {
        if (-not (Stop-OwnedService $name $State.$name)) { $allStopped = $false }
        elseif ($State.$name -ne $null) { $State.$name = $null }
    }
    if ($allStopped) {
        if (Test-Path -LiteralPath $StatePath) { Remove-Item -LiteralPath $StatePath -Force }
        Write-Host '本启动器管理的服务已停止；其他进程未作改动。'
        return $true
    }
    Save-State $State
    return $false
}

try {
    if ($Action -eq 'Stop') {
        if (-not (Test-Path -LiteralPath $StatePath)) {
            Write-Host '没有本启动器的运行记录；未终止任何进程。'
            exit 0
        }
        $state = Read-State
        if (Invoke-Stop $state) { exit 0 } else { exit 1 }
    }

    New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
    $state = Read-State
    $startedThisCall = New-Object 'System.Collections.Generic.List[string]'

    foreach ($name in @('backend', 'frontend')) {
        $owned = $state.$name
        if ($null -ne $owned -and -not (Test-OwnedRoot $owned)) { $state.$name = $null }
    }

    $needsStart = ($null -eq $state.backend -or $null -eq $state.frontend)
    if ($needsStart) {
        $pythonPath = Join-Path $Root '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $pythonPath)) { throw '未找到项目 Python 环境 .venv\Scripts\python.exe。' }
        if ($null -eq (Get-Command 'npm.cmd' -ErrorAction SilentlyContinue)) { throw '找不到 npm.cmd，请先安装 Node.js。' }
        Set-RealEnvironment
    }

    foreach ($pair in @(@{name='backend'; port=$BackendPort}, @{name='frontend'; port=$FrontendPort})) {
        $name = [string]$pair.name
        $port = [int]$pair.port
        $listeners = @(Get-ListenerIds $port)
        if ($listeners.Count -gt 0) {
            $owned = $state.$name
            $listenerOwned = $owned -and (Test-OwnedRoot $owned) -and (Test-ListenerOwnedBy $port $owned)
            if (-not $listenerOwned) {
                throw "端口 $port 已被本启动器之外的进程占用；未终止该进程。"
            }
        }
    }

    if ($null -eq $state.backend) {
        $null = Start-OwnedService 'backend' $state
        $startedThisCall.Add('backend')
    }
    if ($null -eq $state.frontend) {
        $null = Start-OwnedService 'frontend' $state
        $startedThisCall.Add('frontend')
    }

    Write-Host '等待真实后端与首页就绪……'
    $deadline = [DateTime]::UtcNow.AddSeconds(100)
    $readyBackend = $false
    $readyFrontend = $false
    $backendDiagnostic = $null
    $frontendDiagnostic = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not $readyBackend) { $readyBackend = Test-ServiceReady 'backend' $state.backend ([ref]$backendDiagnostic) }
        if (-not $readyFrontend) { $readyFrontend = Test-ServiceReady 'frontend' $state.frontend ([ref]$frontendDiagnostic) }
        if ($readyBackend -and $readyFrontend) { break }
        if (($null -eq (Get-ProcessInfo ([int]$state.backend.pid))) -or ($null -eq (Get-ProcessInfo ([int]$state.frontend.pid)))) { break }
        Start-Sleep -Seconds 1
    }
    if (-not ($readyBackend -and $readyFrontend)) {
        Write-Host "就绪检查结果：后端=$readyBackend，首页=$readyFrontend。"
        $diagnosticEntries = @{
            backend = $backendDiagnostic
            frontend = $frontendDiagnostic
        }
        $cleanupStatuses = @{
            backend = 'not_started_this_call'
            frontend = 'not_started_this_call'
        }
        foreach ($name in @('frontend', 'backend')) {
            if ($startedThisCall.Contains($name)) {
                $cleanupOutcome = $null
                $null = Stop-OwnedService $name $state.$name -Quiet -Outcome ([ref]$cleanupOutcome)
                $cleanupStatuses[$name] = if ($null -ne $cleanupOutcome) { $cleanupOutcome } else { 'unknown' }
                if ($state.$name -ne $null -and -not (Test-OwnedRoot $state.$name)) { $state.$name = $null }
            }
        }

        $diagnosticsPath = Join-Path $StateDirectory ("launcher-diagnostics-{0}.jsonl" -f [Guid]::NewGuid().ToString('N'))
        $diagnosticsWritten = $true
        foreach ($name in @('backend', 'frontend')) {
            $entry = $diagnosticEntries[$name]
            if ($null -eq $entry) {
                $entry = [pscustomobject]@{
                    service = $name
                    port = if ($name -eq 'backend') { $BackendPort } else { $FrontendPort }
                    root_owned = $null
                    listener_query_passed = $null
                    listener_query_exception_category = $null
                    listener_query_error_category = $null
                    listener_query_failure_kind = $null
                    listener_present = $null
                    listener_owned = $null
                    http_status = $null
                    probe_passed = $null
                    exception_category = $null
                    ready = if ($name -eq 'backend') { [bool]$readyBackend } else { [bool]$readyFrontend }
                    cleanup_status = $null
                }
            }
            $entry.cleanup_status = $cleanupStatuses[$name]
            if (-not (Write-LauncherDiagnostic -Path $diagnosticsPath -Entry $entry)) { $diagnosticsWritten = $false }
        }
        $diagnosticsWriteStatus = if ($diagnosticsWritten) { 'complete' } else { 'partial_or_failed' }
        Write-Host "启动诊断记录（写入状态=$diagnosticsWriteStatus）：$diagnosticsPath"
        Save-State $state
        throw '服务在限定时间内未就绪；本次新启动的服务已尝试停止。查看临时日志目录获取启动错误。'
    }

    Start-Process -FilePath $HomeUrl | Out-Null
    Write-Host "TraderLens 首页已在默认浏览器打开：$HomeUrl"
    Write-Host '首页可进入记录成交或持仓/观察；成交表单只登记已完成的交易，不会下单。'
    Write-Host '再次运行 start.bat 会复用本启动器的服务；运行 stop.bat 只停止本启动器管理的进程树。'
    exit 0
} catch {
    Write-Host "启动器失败：$($_.Exception.Message)" -ForegroundColor Red
    if (Test-Path -LiteralPath $StateDirectory) { Write-Host "运行日志目录：$StateDirectory" }
    exit 1
}
