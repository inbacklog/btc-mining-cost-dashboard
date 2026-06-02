$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

& $Python -m pip install -r requirements.txt
& $Python -m pip install pyinstaller

$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name", "BTC-Mining-Cost-Dashboard",
    "--add-data", "app.py;.",
    "--collect-all", "streamlit",
    "--collect-all", "streamlit_autorefresh",
    "--collect-all", "plotly",
    "--collect-all", "yfinance",
    "--hidden-import", "streamlit.web.cli"
)

$BasePrefix = (& $Python -c "import sys; print(sys.base_prefix)")
$CondaBin = Join-Path $BasePrefix "Library\bin"
if (Test-Path $CondaBin) {
    foreach ($DllName in @("libexpat.dll", "liblzma.dll", "libbz2.dll", "ffi.dll", "sqlite3.dll")) {
        $DllPath = Join-Path $CondaBin $DllName
        if (Test-Path $DllPath) {
            $PyInstallerArgs += @("--add-binary", "$DllPath;.")
        }
    }
}

$PyInstallerArgs += "run_dashboard.py"

& $Python -m PyInstaller @PyInstallerArgs

Write-Host ""
Write-Host "Built executable:"
Write-Host (Join-Path $ProjectRoot "dist\BTC-Mining-Cost-Dashboard.exe")
