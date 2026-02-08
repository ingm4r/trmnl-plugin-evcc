# TRMNL EVCC Collector
# Collects data from EVCC and sends to TRMNL webhook
#
# Build:
#   docker build -t trmnl-evcc-collector ./collector
#
# Run with config file (recommended):
#   docker run -d \
#     -v ./config.yaml:/app/config.yaml:ro \
#     trmnl-evcc-collector
#
# Run with environment variables:
#   docker run -d \
#     -e EVCC_URL=http://evcc:7070 \
#     -e WEBHOOK_URL=https://usetrmnl.com/api/custom_plugins/xxx \
#     -e INTERVAL=300 \
#     trmnl-evcc-collector

FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy collector script
COPY evcc_collector.py /app/

# Copy example config for reference
COPY config.example.yaml /app/

# Environment variables for env-var mode (optional)
ENV EVCC_URL=""
ENV WEBHOOK_URL=""
ENV INTERVAL="0"
ENV TZ="UTC"
ENV MAX_LOADPOINTS=""
ENV POWER_UNIT=""
ENV SERVE_PORT=""
EXPOSE 8080

# Entry point script
COPY --chmod=755 <<'EOF' /app/entrypoint.sh
#!/bin/bash
set -e

# Check if config file exists
if [[ -f "/app/config.yaml" ]]; then
    echo "Starting with config file..."
    ARGS="--config /app/config.yaml"
    if [[ -n "$SERVE_PORT" ]]; then
        ARGS="$ARGS --serve --port $SERVE_PORT"
    fi
    exec python /app/evcc_collector.py $ARGS
fi

# Fall back to environment variables
if [[ -z "$EVCC_URL" ]]; then
    echo "ERROR: Either mount a config.yaml file or provide EVCC_URL environment variable"
    exit 1
fi

# Build command arguments from environment variables
ARGS="-u $EVCC_URL"

if [[ -n "$WEBHOOK_URL" ]]; then
    ARGS="$ARGS -w $WEBHOOK_URL"
fi

if [[ -n "$INTERVAL" && "$INTERVAL" != "0" ]]; then
    ARGS="$ARGS -i $INTERVAL"
fi

if [[ -n "$TZ" ]]; then
    ARGS="$ARGS -z $TZ"
fi

if [[ -n "$MAX_LOADPOINTS" ]]; then
    ARGS="$ARGS --max-loadpoints $MAX_LOADPOINTS"
fi

if [[ -n "$POWER_UNIT" ]]; then
    ARGS="$ARGS --power-unit $POWER_UNIT"
fi

if [[ -n "$SERVE_PORT" ]]; then
    ARGS="$ARGS --serve --port $SERVE_PORT"
fi

# Run the Python collector
exec python /app/evcc_collector.py $ARGS
EOF

ENTRYPOINT ["/app/entrypoint.sh"]
