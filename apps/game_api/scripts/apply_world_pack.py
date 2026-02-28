from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "packages" / "shared_schemas") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))
if str(REPO_ROOT / "packages" / "rules_engine") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "rules_engine"))

from apps.game_api.app.services.world_pack_files import load_world_pack_specs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a file-based world pack quest set to a world via game_api.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="Game API base url.")
    parser.add_argument("--world-id", required=True, help="Target world id.")
    parser.add_argument(
        "--pack-dir",
        default=str(REPO_ROOT / "world_packs" / "urban_occult_v1"),
        help="World pack directory containing manifest.json.",
    )
    parser.add_argument("--requested-by", default="local_cli", help="Audit requested_by value.")
    parser.add_argument("--source", default="world_pack_apply_script", help="Audit source value.")
    args = parser.parse_args()

    pack_dir = Path(args.pack_dir).resolve()
    loaded = load_world_pack_specs(pack_dir)
    payload = {
        "world_id": args.world_id,
        "requested_by": args.requested_by,
        "source": args.source,
        "specs": loaded.raw_specs,
    }
    body = json.dumps(payload).encode("utf-8")
    endpoint = f"{args.base_url.rstrip('/')}/v1/quest-specs/apply"
    req = urllib_request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib_request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            print(raw)
            print(
                f"PASS: applied world pack {loaded.manifest.pack_id} ({loaded.manifest.version}) to {args.world_id}"
            )
            return 0
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="ignore")
        print(f"FAIL: HTTP {exc.code} - {text}")
        return 1
    except URLError as exc:
        print(f"FAIL: network error - {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
