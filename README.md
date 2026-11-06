# lg-thinq-temperature-history

Collect temperature history from LG ThinQ air conditioners, store it in Supabase,
and compare rooms with outdoor weather in a local dashboard.

A short Python job runs locally or through GitHub Actions. The dashboard reads the
saved history, so collection does not require an always-on home computer.

## Features

- Discover ACs registered to one LG ThinQ account.
- Save room temperature, target temperature, power, mode, fan, and raw status.
- Optionally collect city-level outdoor temperature from Open-Meteo.
- Compare selected rooms and outdoor weather in one interactive chart.
- Rename rooms locally without changing their stored history.
- View latest readings, power state, collection age, and inside/outside differences.
- Distinguish overlapping readings using marker shapes, line patterns, and legend selection.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (manages Python and dependencies).
- Supported ACs registered in the LG ThinQ app.
- A ThinQ personal access token with **Device list retrieval** and **Device Status Inquiry** scopes.
- A Supabase project with its **Data API enabled** and a server-side secret key.

The optional **Device Energy Consumption Inquiry** scope enables the energy-profile
inspection command. Energy-history collection is not implemented yet.

## Quick start

Clone this repository, enter its directory, and run:

```sh
uv sync --locked
cp .env.example .env
```

Copy the template only for a fresh setup; preserve an existing `.env`.
Set these values:

| Variable | Purpose |
| --- | --- |
| `LG_ACCESS_TOKEN` | Your private ThinQ personal access token |
| `LG_COUNTRY` | LG account country; default `BR` |
| `LG_REGION` | API region; default `aic` for Brazil |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SECRET_KEY` | Server-side `sb_secret_...` key or legacy service-role JWT |

The template also includes `LG_CLIENT_ID` and `LG_API_KEY`. The latter is the public
application key distributed in LG's SDK, distinct from your personal access token.
Country and region must match your account; consult the
[LG SDK country mapping](https://github.com/thinq-connect/pythinqconnect/blob/main/thinqconnect/country.py)
for countries outside Brazil.

### Create the database table

Local SQL schemas and migration files are intentionally gitignored. For a fresh
installation, run this SQL in the Supabase SQL Editor. It is also safe to rerun
against the initial table to add the outdoor-weather columns.

```sql
-- Run once in the Supabase SQL Editor.
create table if not exists public.readings (
  id uuid primary key,
  device_id text not null,
  alias text not null,
  collected_at timestamptz not null,
  temperature double precision,
  target_temperature double precision,
  unit text,
  power text,
  mode text,
  fan text,
  raw jsonb not null
);
create index if not exists readings_time_idx on public.readings (collected_at, id);
create index if not exists readings_device_time_idx on public.readings (device_id, collected_at);
alter table public.readings enable row level security;
revoke all on public.readings from anon, authenticated;
grant select, insert on public.readings to service_role;
-- No public policies: access is through the trusted Python process only.

-- Add outdoor reference fields without modifying historical indoor readings.
alter table public.readings
  add column if not exists outdoor_temperature_c double precision,
  add column if not exists weather_time timestamptz,
  add column if not exists weather_collected_at timestamptz,
  add column if not exists weather_location text,
  add column if not exists weather_latitude double precision,
  add column if not exists weather_longitude double precision,
  add column if not exists weather_source text;
```

RLS is enabled, public table privileges are revoked, and no public policies are
created. The collector and dashboard access the Data API from Python using the
server-side secret key. That key bypasses RLS and must stay private.

### Test access and collect

```sh
uv run main.py devices
uv run main.py status DEVICE_ID
uv run collect.py --dry-run
uv run collect.py
```

`--dry-run` fetches real LG/weather data and prints it without writing to Supabase.
Each normal run saves all discovered ACs, including powered-off units. Failed device
requests do not discard successful readings; failures return a nonzero exit code.
Weather failures also preserve indoor readings. Automatic retries are not implemented.

Other inspection commands:

```sh
uv run main.py profile DEVICE_ID
uv run main.py energy-profile DEVICE_ID
```

### Start the dashboard

Run from the repository root so Streamlit loads the included theme:

```sh
uv run streamlit run dashboard.py --server.address 127.0.0.1
```

Open the local URL printed by Streamlit. Use the sidebar to select history and rooms.
Click a legend name to isolate a series; Shift-click selects several and double-click
resets the selection. The history table is collapsed below the chart.
Credentials stay in the Python process. This local dashboard has no login; keep it
bound to localhost.

## Outdoor weather

Set these optional values in `.env`:

```dotenv
WEATHER_LOCATION=Your city
WEATHER_LATITUDE=
WEATHER_LONGITUDE=
```

Fill in decimal city-level coordinates; an exact home address is unnecessary.
Leave both coordinates empty to disable weather. No weather API key is needed.
One Open-Meteo request is made per collection run.

Outdoor temperatures are regional weather-model estimates, not measurements at your
house. The comparison provides context; it does not establish insulation quality or
AC efficiency. Open-Meteo attribution is shown in the dashboard. See its
[API documentation and usage terms](https://open-meteo.com/en/docs) before using the
hosted service commercially.

## Friendly room names

Create a local `device_names.json` hashmap:

```json
{
  "LG alias or device ID": "Living room",
  "Another LG alias or device ID": "Bedroom"
}
```

Use your actual aliases or IDs. Device IDs take priority over aliases and stay stable
if an LG alias changes. Unmapped devices keep their LG names. A generic
`device_names.example.json` is included; your populated map is gitignored.
Names apply to historical readings in the dashboard without modifying the database.

## Scheduled collection with GitHub Actions

The included `.github/workflows/collect.yml` runs every 30 minutes, at minutes **00 and 30**
each hour and supports manual runs through **Run workflow**.

1. Push the source and `uv.lock` to the default branch.
2. Add repository Actions secrets: `LG_ACCESS_TOKEN`, `SUPABASE_URL`, and `SUPABASE_SECRET_KEY`.
3. Optionally add repository variables `LG_COUNTRY` and `LG_REGION` (defaults: `BR` / `aic`).
4. For weather, add `WEATHER_LOCATION`, `WEATHER_LATITUDE`, and `WEATHER_LONGITUDE` as repository secrets or variables. Secrets take priority when both exist.
5. Trigger a manual run and confirm readings appear in Supabase.

No `.env` file is needed in Actions. Schedules are best effort and can be delayed or
dropped. Public-repository schedules can disable after 60 days without repository
activity; private repositories consume your plan's runner allowance. See
[GitHub scheduling documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Time and data semantics

- `collected_at`: shared UTC timestamp for our collection run; used for every chart series.
- `weather_time`: Open-Meteo source/model time, retained for freshness checks.
- `weather_collected_at`: time our weather request completed.

The chart and table display **America/Sao_Paulo** time (Curitiba, UTC−3).
Weather points use the associated `collected_at`, so the source time does not shift
them away from indoor readings. Weather references older than 45 minutes relative
to collection, or dated in the future, are excluded from comparisons.

Earlier data may contain separate per-device collection timestamps. Those remain as
stored. LG status responses do not establish sensor measurement time: successful
polls can contain unchanged or stale readings, especially while units are off.
Identical readings are retained; lines may span missing samples. Historical weather
backfill and automated retention/backups are not implemented.

## Repository contents

| File | Purpose |
| --- | --- |
| `main.py` | Read-only LG API inspection commands |
| `collect.py` | One-shot collection and normalization |
| `weather.py` | Optional Open-Meteo reference |
| `storage.py` | Supabase REST reads and writes |
| `dashboard.py` | Local Streamlit dashboard |
| `.streamlit/config.toml` | Dashboard theme |
| `.env.example` | Credential and location template |
| `.github/workflows/collect.yml` | Scheduled collection |

Local `.env` files, `device_names.json`, `schema.sql`, `schemas/`, and `migrations/`
are excluded from Git. Keep database exports and real API responses out of public
commits too. Ignore rules do not remove files already tracked in an existing Git
repository; inspect staged changes before publishing.

Built on the [LG ThinQ API](https://github.com/thinq-connect/pythinqconnect),
[Supabase](https://supabase.com/), [Streamlit](https://streamlit.io/), and
[Open-Meteo](https://open-meteo.com/) (weather data: CC BY 4.0).
This is an independent project, not an official LG product.
