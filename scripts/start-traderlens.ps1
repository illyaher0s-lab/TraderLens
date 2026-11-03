param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'

function Assert-PortsAvailable {
    param([int[]]$Ports = @(8010, 3000))

    foreach ($port in $Ports) {
        try {
            $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop)
        } catch {
            $queryError = $_
            if (
                $queryError.CategoryInfo.Category -eq [System.Management.Automation.ErrorCategory]::ObjectNotFound -and
                $queryError.FullyQualifiedErrorId -ceq 'CmdletizationQuery_NotFound,Get-NetTCPConnection'
            ) {
                $listeners = @()
            } else {
                $category = [string]$queryError.CategoryInfo.Category
                $errorId = [string]$queryError.FullyQualifiedErrorId
                throw "无法核实端口 $port（$category/$errorId）；为避免接管其他服务，已取消启动。"
            }
        }
        if ($listeners.Count -gt 0) {
            throw "端口 $port 已被占用；没有启动或停止任何进程。"
        }
    }
}

function Wait-ForWebsite {
    param(
        [int]$Attempts = 60,
        [int]$DelaySeconds = 1,
        [string]$BackendUrl = 'http://127.0.0.1:8010/api/research/service-health',
        [string]$HomeUrl = 'http://localhost:3000/'
    )

    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        $backendReady = $false
        $frontendReady = $false
        try {
            $health = Invoke-RestMethod -Uri $BackendUrl -TimeoutSec 2
            $backendReady = $health.is_healthy -eq $true -and $health.is_real_mode -eq $true
        } catch {
            $backendReady = $false
        }
        try {
            $response = Invoke-WebRequest -Uri $HomeUrl -UseBasicParsing -TimeoutSec 2
            $frontendReady = $response.StatusCode -eq 200
        } catch {
            $frontendReady = $false
        }
        if ($backendReady -and $frontendReady) { return $true }
        if ($attempt + 1 -lt $Attempts -and $DelaySeconds -gt 0) {
            Start-Sleep -Seconds $DelaySeconds
        }
    }
    return $false
}

function Start-TraderLens {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($env:RESEARCH_LLM_API_KEY)) {
        throw '缺少 RESEARCH_LLM_API_KEY。请一次性配置 Windows 用户环境变量后重新登录；启动器不会逐次询问或显示密钥。'
    }
    if ([string]::IsNullOrWhiteSpace($env:TUSHARE_TOKEN)) {
        throw '缺少 TUSHARE_TOKEN。请一次性配置 Windows 用户环境变量后重新登录；启动器不会逐次询问或显示令牌。'
    }

    $pythonPath = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "找不到当前工作区的 Python 环境：$pythonPath"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $root 'node_modules\next\dist\bin\next'))) {
        throw '找不到 Next.js 依赖；请先在当前工作区安装项目依赖。'
    }
    $npm = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
    if ($null -eq $npm) {
        throw '找不到 npm.cmd；请先安装 Node.js。'
    }
    $commandProcessor = [Environment]::GetEnvironmentVariable('ComSpec', 'Process')
    if ([string]::IsNullOrWhiteSpace($commandProcessor)) {
        throw '找不到 Windows 命令解释器配置 ComSpec。'
    }

    Assert-PortsAvailable

    $env:RESEARCH_CONVERSATION_MODE = 'real'
    $env:SERENITY_EXECUTION_MODE = 'two_phase'
    $env:BACKEND_PORT = '8010'
    $env:NEXT_PUBLIC_API_BASE_URL = 'http://localhost:8010'
    if ([string]::IsNullOrWhiteSpace($env:TUSHARE_API_URL)) {
        $env:TUSHARE_API_URL = 'https://ts.gyzcloud.top/api'
    }

    $backendCommand = 'title TraderLens Backend & cd /d "{0}" && "{1}" -m uvicorn backend.app.main:app --app-dir "{0}" --host 127.0.0.1 --port 8010' -f $root, $pythonPath
    $frontendCommand = 'title TraderLens Frontend & cd /d "{0}" && call "{1}" run dev -- --hostname 127.0.0.1 --port 3000' -f $root, $npm.Source

    Write-Host '启动后端和前端；两个可见窗口会保留输出，便于查看错误。'
    Start-Process -FilePath $commandProcessor -ArgumentList @('/d', '/k', $backendCommand) -WorkingDirectory $root -WindowStyle Normal | Out-Null
    Start-Process -FilePath $commandProcessor -ArgumentList @('/d', '/k', $frontendCommand) -WorkingDirectory $root -WindowStyle Normal | Out-Null

    Write-Host '正在检查真实模式后端和首页……'
    if (-not (Wait-ForWebsite)) {
        throw '后端或首页未在限定时间内就绪。请查看两个服务窗口；按 Ctrl+C 停止各自服务。'
    }

    Start-Process -FilePath 'http://localhost:3000/' -WindowStyle Normal | Out-Null
    Write-Host 'TraderLens 首页已打开：http://localhost:3000/'
    Write-Host '停止服务：分别在 TraderLens Backend 和 TraderLens Frontend 窗口按 Ctrl+C，或关闭对应窗口。'
}

try {
    Start-TraderLens -ProjectRoot $ProjectRoot
    exit 0
} catch {
    Write-Host "[错误] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
