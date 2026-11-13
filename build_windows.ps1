param([string]$DistPath = ".\Windows版")

$ErrorActionPreference = "Stop"
Push-Location -LiteralPath $PSScriptRoot
$originalPath = $env:Path
try {
    # Qt 使用 Windows 自带的 ICU。隔离其他程序的 DLL 搜索路径。
    $env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
    $build = Join-Path $PSScriptRoot ".build"
    $env:TEMP = Join-Path $build "temp"
    $env:TMP = $env:TEMP
    $env:MPLCONFIGDIR = Join-Path $build "mpl"
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $build "pyinstaller-cache"
    New-Item -ItemType Directory -Path $env:TEMP,$env:MPLCONFIGDIR,$env:PYINSTALLER_CONFIG_DIR -Force | Out-Null
    $env:PYTHONDONTWRITEBYTECODE = "1"

    $packageArgs = @(
        "--noconfirm", "--onedir", "--windowed", "--name", "EconMetricsStudio",
        "--distpath", $DistPath, "--workpath", ".\.build\package", "--specpath", ".\.build",
        "--paths", $PSScriptRoot, "--hidden-import", "xlrd",
        "--exclude-module", "IPython", "--exclude-module", "tkinter", "--exclude-module", "pytest",
        ".\main_app.py"
    )
    & ".\.venv\Scripts\python.exe" -m PyInstaller @packageArgs
    if ($LASTEXITCODE -ne 0) { throw "Windows 打包失败，退出码 $LASTEXITCODE。" }

    # 旧的分析缓存也可能带入同名 DLL，避免成品覆盖 Windows 的 ICU。
    $internal = Join-Path $DistPath "EconMetricsStudio\_internal"
    Get-ChildItem -LiteralPath $internal -File | Where-Object {
        $_.Name -match '^(icuuc|icuin|icudt\d+)\.dll$'
    } | ForEach-Object { Remove-Item -LiteralPath $_.FullName }
} finally {
    $env:Path = $originalPath
    Pop-Location
}
