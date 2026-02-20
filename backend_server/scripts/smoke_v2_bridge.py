import argparse
import json
import sys

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test for backend_server -> backend_v2 bridge mode.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="backend_server base URL")
    parser.add_argument("--username", required=True, help="legacy backend username")
    parser.add_argument("--password", required=True, help="legacy backend password")
    parser.add_argument("--world-name", default="Bridge Smoke World", help="world name for smoke run")
    parser.add_argument("--command", default="Ich schaue mich um.", help="test command to send")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        with httpx.Client(timeout=30.0) as client:
            token_response = client.post(
                f"{base_url}/token",
                data={"username": args.username, "password": args.password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_response.raise_for_status()
            token = token_response.json().get("access_token")
            if not token:
                print("FAIL: /token returned no access_token")
                return 1

            headers = {"Authorization": f"Bearer {token}"}

            world_payload = {
                "world_name": args.world_name,
                "lore": "Smoke lore",
                "char_name": "SmokeHero",
                "backstory": "Smoke test character.",
                "attributes": {
                    "Strength": 10,
                    "Dexterity": 10,
                    "Constitution": 10,
                },
                "template_key": "system_fantasy",
            }
            world_response = client.post(f"{base_url}/worlds/create", json=world_payload, headers=headers)
            world_response.raise_for_status()
            world_data = world_response.json()
            world_id = int(world_data["world_id"])
            player_id = int(world_data["player_id"])

            command_payload = {
                "command": args.command,
                "world_id": world_id,
                "player_id": player_id,
            }
            command_response = client.post(f"{base_url}/command", json=command_payload, headers=headers)
            command_response.raise_for_status()
            command_data = command_response.json()

            summary_response = client.get(
                f"{base_url}/load_game_summary",
                params={"world_id": world_id, "player_id": player_id},
                headers=headers,
            )
            summary_response.raise_for_status()
            summary_data = summary_response.json()

    except httpx.HTTPStatusError as exc:
        body = exc.response.text if exc.response is not None else str(exc)
        print(f"FAIL: HTTP {exc.response.status_code} - {body}")
        return 1
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print("PASS: backend_server bridge smoke succeeded")
    print(
        json.dumps(
            {
                "world_id": world_id,
                "player_id": player_id,
                "initial_story": world_data.get("initial_story", ""),
                "turn_response": command_data.get("response", ""),
                "summary": summary_data.get("response", ""),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
