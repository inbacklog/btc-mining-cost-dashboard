# BTC Mining Cost Dashboard

A Streamlit dashboard for comparing BTC market price with an estimated mining production-cost model. It combines price history, moving averages, RSI, volume, network mining metrics, cost assumptions, and a historical accumulation-opportunity score.

**[Open the dashboard](https://inbacklog.github.io/btc-mining-cost-dashboard/)**. The browser runs the same Streamlit entry point, sidebar, calculations, charts and manual as the Windows application using [Stlite](https://github.com/whitphx/stlite). The first visit downloads Python and the chart libraries. [Downloads and project details](https://inbacklog.github.io/btc-mining-cost-dashboard/project.html).

GitHub Actions publishes Yahoo Finance OHLCV snapshots (USD and EUR, daily, weekly and monthly) and mining metrics daily at 08:37 UTC. Binance mode requests spot candles directly from its public market-data endpoint, subject to exchange availability. Mining data includes [Coin Metrics Community Data](https://github.com/coinmetrics/data) (CC BY-NC 4.0). A failed refresh leaves the last successful site available. For a local preview, install the Python requirements, run `python build_pages.py`, then `python -m http.server 8000 --directory docs` and open `http://localhost:8000/`.

This project is intended for research and education. It is not financial advice.

## Features

- BTC price history from Yahoo Finance or Binance spot data.
- Mining metrics from Coin Metrics, with CSV and Blockchain.com fallbacks.
- Estimated electrical cost floor and total production cost per BTC.
- Optional calibration to an external production-cost reference.
- Moving averages, 200-week MA, Bollinger Bands, RSI, volume, and price/cost ratio.
- Separate direct chart for BTC price versus mining-cost lines.
- Historical accumulation-opportunity score for context.
- Date-window controls that keep charts aligned and readable.

<img width="1392" height="626" alt="image" src="https://github.com/user-attachments/assets/c1cc5143-4600-40cf-901b-d435845d202b" />

<img width="1560" height="527" alt="image" src="https://github.com/user-attachments/assets/6086e5b0-63c3-4f69-b302-8eafad7a3b26" />

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

Windows users can download the executable from the repository's **Releases** page when a release is available.

Developers can rebuild the executable locally with:

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

## License

No license has been selected yet.
