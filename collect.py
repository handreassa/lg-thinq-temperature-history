"""Collect all ACs once; failures on one device do not discard other readings."""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
import httpx
from main import fetch
from storage import save_readings
from weather import fetch_weather


def normalize(device, state, collected_at=None):
    temperature = state.get("temperature", {})
    return {
        "id": str(uuid.uuid4()),
        "device_id": device["deviceId"],
        "alias": device.get("deviceInfo", {}).get("alias", device["deviceId"]),
        "collected_at": collected_at or datetime.now(timezone.utc).isoformat(),
        "temperature": temperature.get("currentTemperature"),
        "target_temperature": temperature.get("targetTemperature"),
        "unit": temperature.get("unit"),
        "power": state.get("operation", {}).get("airConOperationMode"),
        "mode": state.get("airConJobMode", {}).get("currentJobMode"),
        "fan": state.get("airFlow", {}).get("windStrength"),
        "raw": state,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print readings without accessing Supabase")
    args = parser.parse_args()
    rows, failed = [], False
    try:
        collected_at = datetime.now(timezone.utc).isoformat()
        devices = fetch("devices")
        for device in devices:
            if device.get("deviceInfo", {}).get("deviceType") != "DEVICE_AIR_CONDITIONER":
                continue
            try:
                from urllib.parse import quote
                state = fetch(f"devices/{quote(device['deviceId'], safe='')}/state")
                rows.append(normalize(device, state, collected_at=collected_at))
            except (ValueError, httpx.HTTPError):
                print("An AC status request failed; continuing with the others.", file=sys.stderr)
                failed = True
        # One weather call per batch. A weather outage must not discard indoor data.
        try:
            weather = fetch_weather()
            if weather:
                for row in rows:
                    row.update(weather)
        except (ValueError, KeyError, TypeError, httpx.HTTPError):
            print("Weather lookup failed; saving indoor readings without outdoor data.", file=sys.stderr)
            failed = True
        if args.dry_run:
            print(json.dumps(rows, indent=2))
        else:
            save_readings(rows)
            print(f"Saved {len(rows)} readings.")
        return int(failed)
    except (ValueError, httpx.HTTPError):
        print("Collection failed. Check configuration, API access, and database schema.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
