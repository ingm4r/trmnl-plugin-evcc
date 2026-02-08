# Terminus / BYOS Setup

Guide for using the EVCC collector with a self-hosted
[Terminus (BYOS)](https://github.com/usetrmnl/byos_hanami) instance.

## Architecture

Instead of pushing data to TRMNL cloud webhooks, the collector runs a
lightweight HTTP server. A Terminus Extension polls this endpoint for
JSON data and renders Liquid templates server-side.

```
EVCC API -> Collector <-- GET JSON -- Terminus Extension -> render -> device
```

## Prerequisites

- [Terminus](https://github.com/usetrmnl/byos_hanami) running and accessible
- EVCC instance accessible from the collector container
- Both containers on the same Docker network (or reachable via hostname)

## 1. Configure the Collector

In your `config.yaml`, enable serve mode and remove or omit the `webhook` field:

```yaml
interval: 300
timezone: Europe/Berlin

evcc_url: http://evcc:7070

max_loadpoints: 2
power_unit: auto

serve:
  enabled: true
  port: 8080
```

## 2. Run with Docker Compose

```yaml
services:
  trmnl-evcc-collector:
    image: ghcr.io/ingm4r/trmnl-evcc-collector:latest
    container_name: trmnl-evcc-collector
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    environment:
      - TZ=Europe/Berlin
      - SERVE_PORT=8080
    ports:
      - "8080:8080"
```

Or set `SERVE_PORT=8080` to enable serve mode without a config file.

## 3. Verify the Endpoint

```bash
curl http://localhost:8080/
# Returns: {"status": "ok", "endpoint": "/data/evcc"}

curl http://localhost:8080/data/evcc
# Returns: {"site_title": "...", "energy": {...}, "loadpoints": [...], ...}
```

> **Note:** The first request after startup may return 404 until the
> first collection cycle completes (up to `interval` seconds).

## 4. Create a Terminus Extension

1. Open your Terminus dashboard
2. Go to **Extensions -> New Extension**
3. Configure:
   - **Name:** EVCC Solar Charging
   - **URI:** `http://trmnl-evcc-collector:8080/data/evcc`
   - **Kind:** Poll
   - **Schedule:** 5 minutes (match your collector interval)
   - **Template:** paste the contents of [`src/terminus/full.liquid`](../src/terminus/full.liquid)
   - **Model:** select your device model
4. Save and add the generated screen to your device playlist

## Template Notes

The Terminus template (`src/terminus/full.liquid`) differs from the Cloud
template (`src/full.liquid`) in two ways:

- **Data access:** Terminus merges polled JSON data directly into the
  template context at the top level. Data fields like `energy`, `battery`,
  and `loadpoints` are accessed directly (e.g., `{{ energy.pv_power_formatted }}`).
  This is the same as the Cloud template — both use top-level access.
- **Settings:** `trmnl.plugin_settings` is not available on Terminus. The
  Terminus template uses hardcoded defaults instead. Customize these by
  editing the `{% assign %}` blocks at the top of the template.

## Troubleshooting

### Collector not reachable from Terminus

Ensure both containers are on the same Docker network so Terminus can
reach the collector by container name.

### Data shows as empty

Check that the collector has completed at least one collection cycle:

```bash
docker logs trmnl-evcc-collector
```

### Template rendering errors

- Verify the template does **not** use `extension.values.*` for data access.
  Polled data is merged directly into the template context at the top level.
- Test with the raw JSON endpoint first to confirm the data structure matches
  what your template expects.
