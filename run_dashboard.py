from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    """Return a path that works both from source and from a PyInstaller bundle."""
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


def main() -> None:
    app_path = resource_path("app.py")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_PORT", "8502")

    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        os.environ["STREAMLIT_SERVER_PORT"],
        "--server.headless",
        "false",
    ]

    from streamlit.web.cli import main as streamlit_main

    streamlit_main()


if __name__ == "__main__":
    main()
