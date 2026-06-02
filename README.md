# BTC Mining Cost Dashboard

A Streamlit dashboard for comparing BTC market price with an estimated mining production-cost model. It combines price history, moving averages, RSI, volume, network mining metrics, cost assumptions, and a historical accumulation-opportunity score.

This project is intended for research and education. It is not financial advice.

## Preview

Add screenshots to `assets/screenshots/` and reference them here:

```md
![Main dashboard](assets/screenshots/main-dashboard.png)
![Opportunity score](assets/screenshots/opportunity-score.png)
![Cost comparison](assets/screenshots/cost-comparison.png)
```

## Features

- BTC price history from Yahoo Finance or Binance spot data.
- Mining metrics from Coin Metrics, with CSV and Blockchain.com fallbacks.
- Estimated electrical cost floor and total production cost per BTC.
- Optional calibration to an external production-cost reference.
- Moving averages, 200-week MA, Bollinger Bands, RSI, volume, and price/cost ratio.
- Separate direct chart for BTC price versus mining-cost lines.
- Historical accumulation-opportunity score for context.
- Date-window controls that keep charts aligned and readable.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py --server.port 8502
```

Then open:

```text
http://localhost:8502
```

If you already created the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py --server.port 8502
```

## Windows Executable

You can build a local Windows executable that starts the dashboard with a double click:

```powershell
.\build_exe.ps1
```

The generated file will be:

```text
dist\BTC-Mining-Cost-Dashboard.exe
```

For GitHub, the cleanest approach is to keep the source code in the repository and upload the `.exe` under **Releases** as a downloadable asset.

## Model Notes

The dashboard estimates production cost from network hash rate, an editable miner-efficiency assumption, electricity price, facility overhead, and the selected electricity share of total production cost.

There is no official BTC production-cost series. Treat every output as assumption-based context, not as a standalone buy or sell signal.

## Data Sources

- BTC price: Yahoo Finance or Binance spot market data.
- Mining metrics: Coin Metrics Community API / CSV.
- Fallback network metrics: Blockchain.com charts.

## Public Repo Setup

1. Create a new empty public repository on GitHub.
2. Keep it empty: do not initialize it with a README, `.gitignore`, or license if you want a simple first push from this folder.
3. From this project folder, run the commands in the "GitHub Upload" section below.

## GitHub Upload

Replace `YOUR_USERNAME` and `YOUR_REPO` with your GitHub account and repository name:

```powershell
git init
git add .
git commit -m "Initial public release"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

If the remote repository already has files, use this safer flow instead:

```powershell
git init
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git pull origin main --allow-unrelated-histories
git add .
git commit -m "Initial public release"
git push -u origin main
```

## License

Choose a license before publishing. MIT is a common choice for small open-source dashboard projects.
