# 一键启动：后端 pyserver + 前端 Vite（Windows）
# 用法：在项目根目录执行  powershell -ExecutionPolicy Bypass -File scripts/start-all.ps1
# 环境变量：TSX_SKIP_RUST_SERVER、TERMINAL_WS_PORT（默认 8765）

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ServerDir = Join-Path $Root "server"
$WebDir = Join-Path $Root "web"

if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
    Write-Host "[start-all] web/node_modules 不存在，请先执行: cd web; npm install" -ForegroundColor Yellow
    exit 1
}

$pythonExe = $null
$venvPy = Join-Path $ServerDir ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $pythonExe = $venvPy
} else {
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { $pythonExe = $c.Source }
    if (-not $pythonExe) {
        $c2 = Get-Command py -ErrorAction SilentlyContinue
        if ($c2) { $pythonExe = $c2.Source }
    }
}
if (-not $pythonExe) {
    Write-Host "[start-all] 未找到 Python，请安装或创建 server\.venv" -ForegroundColor Red
    exit 1
}

if (-not $env:TERMINAL_WS_PORT) { $env:TERMINAL_WS_PORT = "8765" }

Write-Host "[start-all] 启动后端: $pythonExe pyserver.py (cwd $ServerDir)"
# 新开控制台窗口显示后端日志（调试方便）；不需要可改为 -WindowStyle Hidden
$backend = Start-Process -FilePath $pythonExe -ArgumentList "pyserver.py" -WorkingDirectory $ServerDir -PassThru

try {
    Start-Sleep -Seconds 1
    if ($backend.HasExited) {
        Write-Host "[start-all] 后端已退出，请检查依赖与 server/error.log" -ForegroundColor Red
        exit 1
    }
    Write-Host "[start-all] 启动前端: npm run dev（Ctrl+C 将停止后端）"
    Set-Location $WebDir
    npm run dev
} finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
}
