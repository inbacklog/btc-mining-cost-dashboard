"""Bundle the desktop entry point and its browser-readable data for Pages."""
import base64
import hashlib
import io
import importlib.util
import json
import shutil
import tarfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from app import build_mining_cost_data, fetch_yahoo_price


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "docs" / "generated"
STLITE = "0.85.1"
STLITE_SHA512 = "6eMGS0ErYLnUm4XiSKgbC+leY/zfg07pHgK+ltE8wmbz5+dYEJ69+bwIR4hCKkuV68l+y3KHkCtEQwKXmdTRHw=="
PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.6/full/"


def download(url):
    response = requests.get(url, timeout=(15, 100))
    response.raise_for_status()
    return response.content


def bundle_python():
    directory = OUTPUT / "python"
    directory.mkdir(exist_ok=True)
    lockfile = download(PYODIDE + "pyodide-lock.json")
    packages = json.loads(lockfile)["packages"]
    files = dict.fromkeys(["pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip"])

    def include(package):
        spec = packages[package.replace("_", "-")]
        if spec["file_name"] in files:
            return
        files[spec["file_name"]] = spec["sha256"]
        for dependency in spec["depends"]:
            include(dependency)

    for package in ["micropip", "pandas", "requests", "pyodide-http", "fastparquet",
                    "protobuf", "typing-extensions", "altair", "pillow", "cachetools"]:
        include(package)

    def save(item):
        filename, checksum = item
        content = download(PYODIDE + filename)
        if checksum and hashlib.sha256(content).hexdigest() != checksum:
            raise ValueError(f"Checksum mismatch for {filename}")
        (directory / filename).write_bytes(content)

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(save, files.items()))
    (directory / "pyodide-lock.json").write_bytes(lockfile)


def bundle_runtime():
    archive = download(f"https://registry.npmjs.org/@stlite/browser/-/browser-{STLITE}.tgz")
    if hashlib.sha512(archive).digest() != base64.b64decode(STLITE_SHA512):
        raise ValueError("Browser runtime checksum mismatch")
    runtime = OUTPUT / "runtime"
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        for member in package:
            path = Path(member.name)
            if not member.isfile() or path.parts[:2] != ("package", "build") or path.suffix == ".map":
                continue
            target = runtime.joinpath(*path.parts[2:]).resolve()
            target.relative_to(runtime)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.extractfile(member).read())

    wheels = []
    for name, version in [("blinker", "1.9.0"), ("tenacity", "9.2.1"), ("plotly", "5.24.1")]:
        metadata = json.loads(download(f"https://pypi.org/pypi/{name}/{version}/json"))
        dist = next(d for d in metadata["urls"] if d["filename"].endswith("none-any.whl"))
        wheel = download(dist["url"])
        if hashlib.sha256(wheel).hexdigest() != dist["digests"]["sha256"]:
            raise ValueError(f"{name} wheel checksum mismatch")
        (OUTPUT / dist["filename"]).write_bytes(wheel)
        wheels.append(dist["filename"])
    (OUTPUT / "wheels.json").write_text(json.dumps(wheels), encoding="utf-8")
    component = Path(importlib.util.find_spec("streamlit_autorefresh").origin).parent
    shutil.copytree(component / "frontend" / "build", OUTPUT / "autorefresh", dirs_exist_ok=True)


def write_snapshots():
    today = pd.Timestamp.now(tz="UTC").normalize()
    for ticker in ["BTC-USD", "BTC-EUR"]:
        for interval, max_age in [("1d", 4), ("1wk", 10), ("1mo", 35)]:
            for attempt in range(3):
                prices = fetch_yahoo_price(ticker, interval, None)
                if len(prices) >= 100 and today - prices.time.max() < pd.Timedelta(days=max_age):
                    break
                fetch_yahoo_price.clear()
                time.sleep(2 ** attempt)
            else:
                raise ValueError(f"Incomplete Yahoo snapshot for {ticker} {interval}")
            prices.to_csv(OUTPUT / f"{ticker}-{interval}.csv", index=False)
    mining = build_mining_cost_data(None)
    if len(mining) < 3650 or today - mining.time.max() > pd.Timedelta(days=7):
        raise ValueError("Incomplete mining history")
    mining.to_csv(OUTPUT / "mining.csv", index=False)
    print(f"Mining observations through {mining.time.max():%Y-%m-%d}")


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    bundle_runtime()
    bundle_python()
    write_snapshots()
    shutil.copyfile(ROOT / "app.py", OUTPUT / "app.py")
