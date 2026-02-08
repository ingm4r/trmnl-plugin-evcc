# TRMNL EVCC Solar Charging

[![Docker Image](https://img.shields.io/badge/ghcr.io-trmnl--evcc--collector-blue)](https://ghcr.io/ingm4r/trmnl-evcc-collector)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Monitor your [EVCC](https://evcc.io) solar charging setup on TRMNL e-ink displays. See real-time solar production, grid usage, battery state, and EV charging sessions at a glance.

<!-- ![EVCC Solar Charging](assets/screenshot.png) -->

## Features

- **Solar monitoring** -- real-time PV production with power formatting
- **Grid tracking** -- import/export status with directional indicators
- **Battery status** -- state of charge and charge/discharge power
- **EV charging** -- active sessions with power, energy, duration, and solar percentage
- **Multi-loadpoint** -- support for up to 4 charging points
- **Vehicle details** -- name, SoC, range, and charge limit
- **Charging statistics** -- 30-day and lifetime solar share and costs
- **Tariff display** -- grid price, feed-in rate, and effective home price
- **Multiple layouts** -- full, half_horizontal, half_vertical, and quadrant templates

## Quick Start (TRMNL Cloud)

### 1. Install the Plugin

1. Go to your [TRMNL Dashboard](https://usetrmnl.com)
2. Navigate to **Plugin Directory**
3. Search for **"EVCC Solar Charging"**
4. Click **Add to My Plugins**
5. Copy the **Webhook URL** from the plugin settings

### 2. Set Up the Collector

```bash
# Create a directory for the collector
mkdir trmnl-evcc && cd trmnl-evcc

# Download the required files
curl -O https://raw.githubusercontent.com/ingm4r/trmnl-plugin-evcc/main/collector/docker-compose.yml
curl -O https://raw.githubusercontent.com/ingm4r/trmnl-plugin-evcc/main/collector/config.example.yaml

# Create your config from the example
cp config.example.yaml config.yaml
```

### 3. Configure

Edit `config.yaml` with your EVCC details:

```yaml
interval: 300
timezone: Europe/Berlin

evcc_url: http://evcc:7070

webhook: https://usetrmnl.com/api/custom_plugins/your-webhook-id

max_loadpoints: 2
power_unit: auto
```

### 4. Start the Collector

```bash
docker compose up -d
```

The collector will now send data to your TRMNL device every 5 minutes.

## Quick Start (Self-Hosted Terminus)

If you run a self-hosted [Terminus](https://github.com/usetrmnl/byos_hanami) instance, the collector can serve data via HTTP instead of pushing to webhooks.

A ready-to-use Terminus template is included at [`src/terminus/full.liquid`](src/terminus/full.liquid). See the [Terminus Setup Guide](docs/terminus.md) for full instructions.

## Configuration Reference

### Config File Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `interval` | Collection interval in seconds (0 = run once) | `300` |
| `timezone` | Timezone for display (e.g., `Europe/Berlin`) | `UTC` |
| `evcc_url` | EVCC instance URL | Required |
| `webhook` | TRMNL webhook URL | Optional |
| `max_loadpoints` | Maximum loadpoints to include (1-4) | `4` |
| `power_unit` | Power display: `auto`, `W`, or `kW` | `auto` |
| `serve.enabled` | Enable HTTP server for Terminus | `false` |
| `serve.port` | HTTP server port | `8080` |
| `serve.host` | HTTP server bind address | `0.0.0.0` |

### Environment Variables

For running without a config file (single instance mode):

| Variable | Description | Required |
|----------|-------------|----------|
| `EVCC_URL` | EVCC instance URL | Yes |
| `WEBHOOK_URL` | TRMNL webhook URL | No |
| `INTERVAL` | Collection interval in seconds | No (default: 0) |
| `TZ` | Timezone for display | No (default: UTC) |
| `MAX_LOADPOINTS` | Maximum loadpoints to include | No (default: 4) |
| `POWER_UNIT` | Power display unit | No (default: auto) |
| `SERVE_PORT` | Enable HTTP serve mode on this port | No |

### Plugin Display Settings

Configure these in your TRMNL plugin settings:

| Setting | Description | Options | Default |
|---------|-------------|---------|---------|
| Show Energy Overview | Display solar, grid, and home power | Yes/No | Yes |
| Show Battery | Display battery status | Yes/No | Yes |
| Show Loadpoints | Display charging loadpoint cards | Yes/No | Yes |
| Max Loadpoints | Maximum loadpoints shown | 1-4 | 2 |
| Show Vehicle Details | Display vehicle name, SoC, range | Yes/No | Yes |
| Show Statistics | Display 30-day charging stats | Yes/No | No |
| Show Tariff | Display energy price info | Yes/No | No |
| Power Unit | How to display power values | Auto/W/kW | Auto |

## Docker Compose Examples

### With Config File (Recommended)

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
```

### With Environment Variables

```yaml
services:
  trmnl-evcc-collector:
    image: ghcr.io/ingm4r/trmnl-evcc-collector:latest
    container_name: trmnl-evcc-collector
    restart: unless-stopped
    environment:
      - EVCC_URL=http://evcc:7070
      - WEBHOOK_URL=https://usetrmnl.com/api/custom_plugins/xxx
      - INTERVAL=300
      - TZ=Europe/Berlin
      - MAX_LOADPOINTS=2
```

### Docker Run (Single Instance)

```bash
docker run -d \
  --name trmnl-evcc-collector \
  --restart unless-stopped \
  -e EVCC_URL=http://evcc:7070 \
  -e WEBHOOK_URL=https://usetrmnl.com/api/custom_plugins/xxx \
  -e INTERVAL=300 \
  -e TZ=Europe/Berlin \
  ghcr.io/ingm4r/trmnl-evcc-collector:latest
```

## Template Sizes

The plugin includes templates for all TRMNL screen configurations:

| Template | Resolution | Description |
|----------|-----------|-------------|
| `full` | 800x480 | Energy overview + battery + loadpoints |
| `half_horizontal` | 800x240 | Compact energy bar + active loadpoint |
| `half_vertical` | 400x480 | Energy overview + single loadpoint |
| `quadrant` | 400x240 | Minimal energy stats |
| `terminus/full` | 800x480 | Terminus/BYOS adapted full layout |

## EVCC Requirements

- **EVCC v0.207+** recommended (for full `/api/state` response)
- The collector reads from EVCC's REST API (`/api/state`)
- No API key or authentication required (EVCC exposes its API without auth)
- Ensure the EVCC instance is reachable from the collector container

## Troubleshooting

### View Collector Logs

```bash
docker compose logs -f
```

### Common Issues

**"Cannot connect to EVCC..."**
- Verify your EVCC URL is accessible from the Docker container
- If using `localhost`, try using your machine's IP address or `host.docker.internal`

**Times are wrong**
- Set the correct `timezone` in your config.yaml (e.g., `Europe/Berlin`, `America/New_York`)

**Loadpoints not showing**
- Check `max_loadpoints` is set high enough in both collector config and plugin settings
- Verify EVCC has loadpoints configured

## Development

### Local Development with Docker

```bash
cd collector
cp config.example.yaml config.yaml
# Edit config.yaml with your settings
docker compose -f docker-compose.dev.yml up --build
```

### Running Directly with Python

```bash
cd collector
pip install -r requirements.txt
python evcc_collector.py --config config.yaml
```

### Template Development

Use the [trmnlp](https://github.com/usetrmnl/trmnlp) CLI to preview templates:

```bash
trmnlp serve
# Open http://localhost:4567 to see the rendered template
```

Test data files are available in the `examples/` directory.

## Resources

- [TRMNL](https://usetrmnl.com) -- E-ink smart display
- [EVCC](https://evcc.io) -- Solar charging controller
- [EVCC API Documentation](https://docs.evcc.io/docs/reference/api)
- [Terminus (BYOS)](https://github.com/usetrmnl/byos_hanami) -- Self-hosted TRMNL

## License

MIT License -- see [LICENSE](LICENSE) for details.
