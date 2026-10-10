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

function Test-ListenerOwnedBy([int]$Port, $Owned) {
    foreach ($listenerId in @(Get-ListenerIds $Port)) {
        $current = Get-ProcessInfo ([int]$listenerId)
        for ($depth = 0; $depth -lt 24 -and $null -ne $current; $depth++) {
            if ([int]$current.ProcessId -eq [int]$Owned.pid) { return $true }
            $parentId = [int]$current.ParentProcessId
            if ($parentId -le 0 -or $parentId -eq [int]$current.ProcessId) { break }
            $current = Get-ProcessInfo $parentId
        }
    }
    return $false
}

function Get-ListenerIds([int]$Port) {
    return @(
        Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { [int]$_ }
    )
}

function Test-ServiceReady([string]$Name, $Owned) {
    if (-not (Test-OwnedRoot $Owned)) { return $false }
    $port = if ($Name -eq 'backend') { $BackendPort } else { $FrontendPort }
    if (-not (Test-ListenerOwnedBy $port $Owned)) { return $false }

    try {
        if ($Name -eq 'backend') {
            $health = Invoke-RestMethod -Uri $BackendHealthUrl -TimeoutSec 2
            return ($health.is_healthy -eq $true -and $health.is_real_mode -eq $true)
        }
        $response = Invoke-WebRequest -Uri $HomeReadyUrl -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
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

function Stop-OwnedService([string]$Name, $Owned, [switch]$Quiet) {
    if ($null -eq $Owned) { return $true }
    if (-not (Test-OwnedRoot $Owned)) {
        if ($null -ne (Get-ProcessInfo ([int]$Owned.pid))) {
            if (-not $Quiet) { Write-Host "$Name 的进程身份与启动记录不符，已跳过，未终止。" }
        }
        return $true
    }
    $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
    & $taskkill /F /T /PID ([string]$Owned.pid) 2>$null | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(8)
    do {
        if ($null -eq (Get-ProcessInfo ([int]$Owned.pid))) {
            foreach ($path in @($Owned.runner)) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue } }
            if (-not $Quiet) { Write-Host "$Name 已停止。" }
            return $true
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $Quiet) { Write-Host "$Name 未能确认停止；保留启动记录以便重试。" }
    return $false
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
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not $readyBackend) { $readyBackend = Test-ServiceReady 'backend' $state.backend }
        if (-not $readyFrontend) { $readyFrontend = Test-ServiceReady 'frontend' $state.frontend }
        if ($readyBackend -and $readyFrontend) { break }
        if (($null -eq (Get-ProcessInfo ([int]$state.backend.pid))) -or ($null -eq (Get-ProcessInfo ([int]$state.frontend.pid)))) { break }
        Start-Sleep -Seconds 1
    }
    if (-not ($readyBackend -and $readyFrontend)) {
        Write-Host "就绪检查结果：后端=$readyBackend，首页=$readyFrontend。"
        foreach ($name in @('frontend', 'backend')) {
            if ($startedThisCall.Contains($name)) {
                $null = Stop-OwnedService $name $state.$name -Quiet
                if ($state.$name -ne $null -and -not (Test-OwnedRoot $state.$name)) { $state.$name = $null }
            }
        }
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
