"""Server-side Supabase REST adapter; never expose the secret key to a browser."""
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv


def request(method, *, params=None, rows=None):
    load_dotenv(Path(__file__).with_name(".env"))
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SECRET_KEY", "")
    if not url or not key:
        raise ValueError("Set SUPABASE_URL and SUPABASE_SECRET_KEY in .env.")
    headers = {"apikey": key, "Prefer": "return=minimal,resolution=ignore-duplicates"}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"  # Legacy service_role JWT.
    with httpx.Client(timeout=30) as client:
        response = client.request(method, f"{url}/rest/v1/readings", headers=headers, params=params, json=rows)
        if not response.is_success:
            raise ValueError(f"Supabase HTTP {response.status_code}; check schema and credentials.")
        return response.json() if response.content else None


def save_readings(rows):
    if rows:
        request("POST", rows=rows)


def load_readings(since):
    rows = []
    offset = 0
    while True:
        batch = request("GET", params={"select": "*", "collected_at": f"gte.{since}", "order": "collected_at.asc,id.asc", "limit": "1000", "offset": str(offset)})
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        offset += len(batch)
