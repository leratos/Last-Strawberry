import argparse
import json
import sys
from dataclasses import dataclass

import httpx


@dataclass
class SessionState:
    token: str
    world_id: int
    player_id: int
    turn_outputs: list[str]
    summary: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quick E2E playtest for backend_server bridge mode (happy path + failure path)."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="backend_server base URL")
    parser.add_argument("--username", required=True, help="Legacy backend username")
    parser.add_argument("--password", required=True, help="Legacy backend password")
    parser.add_argument("--world-name", default="Bridge Playtest World", help="World name for this playtest")
    parser.add_argument("--timeout", type=float, default=90.0, help="HTTP timeout seconds")
    parser.add_argument(
        "--commands",
        default="Ich gehe zum Marktplatz.|Ich frage einen Haendler nach Geruechten.|Ich untersuche das Rathaus.",
        help="Pipe-separated list of player commands",
    )
    return parser.parse_args()


def _split_commands(raw: str) -> list[str]:
    parts = [part.strip() for part in raw.split("|")]
    return [part for part in parts if part]


def run_happy_path(client: httpx.Client, base_url: str, username: str, password: str, world_name: str, commands: list[str]) -> SessionState:
    token_response = client.post(
        f"{base_url}/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token_response.raise_for_status()
    token = token_response.json().get("access_token")
    if not token:
        raise RuntimeError("Login succeeded but access_token is missing.")

    headers = {"Authorization": f"Bearer {token}"}

    worlds_before = client.get(f"{base_url}/worlds", headers=headers)
    worlds_before.raise_for_status()

    create_payload = {
        "world_name": world_name,
        "lore": "Quickcheck lore",
        "char_name": "QuickHero",
        "backstory": "Quickcheck character backstory.",
        "attributes": {
            "Strength": 10,
            "Dexterity": 10,
            "Constitution": 10,
            "Intelligence": 10,
            "Wisdom": 10,
            "Charisma": 10,
            "Perception": 10,
        },
        "template_key": "system_fantasy",
    }
    create_response = client.post(f"{base_url}/worlds/create", json=create_payload, headers=headers)
    create_response.raise_for_status()
    create_data = create_response.json()
    world_id = int(create_data["world_id"])
    player_id = int(create_data["player_id"])

    turn_outputs: list[str] = []
    for command in commands:
        command_response = client.post(
            f"{base_url}/command",
            json={"command": command, "world_id": world_id, "player_id": player_id},
            headers=headers,
        )
        command_response.raise_for_status()
        turn_payload = command_response.json()
        response_text = str(turn_payload.get("response") or "").strip()
        if not response_text:
            raise RuntimeError(f"Command returned no narrative: {command}")
        turn_outputs.append(response_text)

    summary_response = client.get(
        f"{base_url}/load_game_summary",
        params={"world_id": world_id, "player_id": player_id},
        headers=headers,
    )
    summary_response.raise_for_status()
    summary_text = str(summary_response.json().get("response") or "").strip()
    if not summary_text:
        raise RuntimeError("Summary endpoint returned empty response.")

    return SessionState(
        token=token,
        world_id=world_id,
        player_id=player_id,
        turn_outputs=turn_outputs,
        summary=summary_text,
    )


def run_failure_path(client: httpx.Client, base_url: str, state: SessionState) -> dict:
    unauthorized_response = client.get(
        f"{base_url}/worlds",
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    if unauthorized_response.status_code != 401:
        raise RuntimeError(f"Expected 401 for invalid token, got {unauthorized_response.status_code}.")

    invalid_world_response = client.post(
        f"{base_url}/command",
        json={
            "command": "Ich teste einen ungueltigen world_id.",
            "world_id": state.world_id + 999999,
            "player_id": state.player_id,
        },
        headers={"Authorization": f"Bearer {state.token}"},
    )
    if invalid_world_response.status_code < 400:
        raise RuntimeError("Expected non-2xx for invalid world command, got success.")

    return {
        "invalid_token_status": unauthorized_response.status_code,
        "invalid_world_status": invalid_world_response.status_code,
        "invalid_world_body": invalid_world_response.text[:300],
    }


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    commands = _split_commands(args.commands)
    timeout_seconds = max(1.0, float(args.timeout))
    if not commands:
        print("FAIL: no commands provided")
        return 1

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            happy = run_happy_path(
                client=client,
                base_url=base_url,
                username=args.username,
                password=args.password,
                world_name=args.world_name,
                commands=commands,
            )
            failures = run_failure_path(client=client, base_url=base_url, state=happy)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text if exc.response is not None else str(exc)
        print(f"FAIL: HTTP {exc.response.status_code} - {body}")
        return 1
    except httpx.TimeoutException as exc:
        print(f"FAIL: timed out (timeout={timeout_seconds}s): {exc}")
        return 1
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    print("PASS: playtest bridge quickcheck succeeded")
    print(
        json.dumps(
            {
                "world_id": happy.world_id,
                "player_id": happy.player_id,
                "commands_executed": len(happy.turn_outputs),
                "last_turn_excerpt": happy.turn_outputs[-1][:220],
                "summary_excerpt": happy.summary[:220],
                "failure_checks": failures,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
