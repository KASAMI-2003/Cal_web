# 安装数字孪生所需的 HTEM 最小运行时（source + Si 示例 dat，约 1MB）
# 不含 example/**/reference 下 VASP 参考算例（体积大且非 Web 运行必需）
#
# 用法（在 tsx-web-app 根目录）：
#   .\scripts\setup_htem.ps1
#   .\scripts\setup_htem.ps1 -SourceRoot "C:\path\to\HTEM-main"

param(
    [string]$SourceRoot = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DestRoot = Join-Path $RepoRoot "server\digital_twin\HTEM-main"

if (-not $SourceRoot) {
    $candidates = @(
        (Join-Path $RepoRoot "..\digital_twin\HTEM-main"),
        (Join-Path $RepoRoot "..\..\digital_twin\HTEM-main"),
        $DestRoot
    )
    foreach ($c in $candidates) {
        $norm = [System.IO.Path]::GetFullPath($c)
        if (Test-Path (Join-Path $norm "source\elasticity.py")) {
            $SourceRoot = $norm
            break
        }
    }
}

if (-not $SourceRoot -or -not (Test-Path (Join-Path $SourceRoot "source\elasticity.py"))) {
    Write-Error "未找到 HTEM-main 源码。请指定 -SourceRoot，或将 HTEM 放在 WEB_FILE/digital_twin/HTEM-main"
}

Write-Host "HTEM 源: $SourceRoot"
Write-Host "安装到: $DestRoot"

New-Item -ItemType Directory -Force -Path $DestRoot | Out-Null
$destSource = Join-Path $DestRoot "source"
if (Test-Path $destSource) {
    Remove-Item -Recurse -Force $destSource
}
Copy-Item -Recurse -Force (Join-Path $SourceRoot "source") $destSource

$siDir = Join-Path $DestRoot "example\5_Si_model"
New-Item -ItemType Directory -Force -Path $siDir | Out-Null
Copy-Item -Force (Join-Path $SourceRoot "example\5_Si_model\Elasticity_cold+NVT_s4.dat") (Join-Path $siDir "Elasticity_cold+NVT_s4.dat")

foreach ($name in @("LICENSE", "README.md")) {
    $src = Join-Path $SourceRoot $name
    if (Test-Path $src) {
        Copy-Item -Force $src (Join-Path $DestRoot $name)
    }
}

Write-Host "HTEM minimal runtime ready. Restart pyserver to enable digital twin surfaces."
