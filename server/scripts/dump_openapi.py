"""Write what the web UI generates its types from: the OpenAPI schema and the
server setting keys.

Run from the server's virtualenv, normally through `npm run gen:api` in web/:

    .venv/bin/python scripts/dump_openapi.py [--out-dir DIR]

The app's lifespan doesn't run, so no database is opened.
"""

import argparse
import json
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from app.main import create_app  # noqa: E402
from app.settings import REGISTRY  # noqa: E402

DEFAULT_OUT_DIR = SERVER_DIR / "web" / "src" / "api"


def _dumps(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "openapi.json").write_text(_dumps(create_app().openapi()))
    (args.out_dir / "server-setting-keys.json").write_text(_dumps(sorted(REGISTRY)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
