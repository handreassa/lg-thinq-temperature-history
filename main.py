"""One-shot, read-only ThinQ requests; suitable for a future scheduled job."""

import argparse
import base64
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import load_dotenv


def fetch(endpoint: str) -> object:
    load_dotenv(Path(__file__).with_name(".env"))  # Environment variables take precedence.
    token = os.getenv("LG_ACCESS_TOKEN", "").strip()
    if not token:
        raise ValueError("Set LG_ACCESS_TOKEN in .env or the environment.")
    region = os.getenv("LG_REGION", "aic").lower()
    if region not in {"aic", "eic", "kic"}:
        raise ValueError("LG_REGION must be aic, eic, or kic.")
    headers = {
        "Authorization": f"Bearer {token}",
        "x-country": os.getenv("LG_COUNTRY", "BR").upper(),
        "x-client-id": os.getenv("LG_CLIENT_ID", "household-info-lg"),
        "x-message-id": base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip("="),
        "x-service-phase": "OP",
        "x-api-key": os.getenv("LG_API_KEY", "v6GFvkweNo7DK7yD3ylIZ9w52aKBU0eJ7wLXkSR3"),
        "Accept": "application/json",
    }
    with httpx.Client(timeout=20) as client:
        response = client.get(f"https://api-{region}.lgthinq.com/{endpoint}", headers=headers)
        response.raise_for_status()
        payload = response.json()
    if payload.get("error"):
        error = payload["error"]
        raise ValueError(f"LG API error code: {error.get('code', 'unknown')}")
    return payload.get("response", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("devices", help="List registered equipment")
    for command in ("status", "profile", "energy-profile"):
        sub = commands.add_parser(command, help=f"Get a device's {command}")
        sub.add_argument("device_id")
    args = parser.parse_args()
    endpoint = "devices"
    if args.command != "devices":
        device = quote(args.device_id, safe="")
        endpoint = {
            "status": f"devices/{device}/state",
            "profile": f"devices/{device}/profile",
            "energy-profile": f"devices/energy/{device}/profile",
        }[args.command]
    try:
        data = fetch(endpoint)
        print(json.dumps({"collected_at": datetime.now(timezone.utc).isoformat(), "data": data}, indent=2))
        return 0
    except httpx.HTTPStatusError as exc:
        print(f"LG request failed: HTTP {exc.response.status_code}. Check token, scopes, country, and region.", file=sys.stderr)
    except (httpx.RequestError, ValueError) as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
