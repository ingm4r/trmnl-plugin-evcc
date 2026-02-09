#!/usr/bin/env python3
"""
TRMNL EVCC Collector

Collects data from EVCC (EV Charge Controller) API and sends to TRMNL webhook
or serves it via HTTP for Terminus/BYOS.

Usage:
    # With config file
    python evcc_collector.py --config config.yaml

    # CLI only
    python evcc_collector.py -u http://evcc:7070 -w https://webhook_url

    # Dry run (print JSON, don't send)
    python evcc_collector.py -u http://evcc:7070 --dry-run
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
import yaml

VERSION = "1.0.0"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class EVCCCollector:
    """Collector for an EVCC instance."""

    MODE_LABELS = {
        "off": "Off",
        "pv": "Solar",
        "minpv": "Min+Solar",
        "now": "Fast",
    }

    def __init__(
        self,
        url: str,
        webhook: Optional[str] = None,
        timezone: Optional[str] = None,
        max_loadpoints: int = 4,
        power_unit: str = "auto",
        verbose: bool = False,
        dry_run: bool = False,
    ):
        self.url = url.rstrip('/')
        self.webhook = webhook
        self.timezone = timezone or os.environ.get('TZ', '')
        self.max_loadpoints = max_loadpoints
        self.power_unit = power_unit
        self.verbose = verbose
        self.dry_run = dry_run

    def _api_request(self) -> Dict[str, Any]:
        """Fetch state from EVCC API.

        GET {url}/api/state — single endpoint, no auth needed.
        EVCC v0.207+ removed the result wrapper; handle both formats.
        """
        api_url = f"{self.url}/api/state"
        try:
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()
            data = response.json()
            # Handle both old (wrapped in 'result') and new (direct) formats
            return data.get('result', data)
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Cannot connect to {self.url}: "
            if "Name or service not known" in str(e) or "nodename nor servname provided" in str(e):
                error_msg += "Host not found (check URL)"
            elif "Connection refused" in str(e):
                error_msg += "Connection refused (is EVCC running?)"
            else:
                error_msg += str(e)
            logger.error(error_msg)
            raise
        except requests.exceptions.Timeout:
            logger.error(f"Cannot connect to {self.url}: Request timed out")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"API request failed: {e}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise

    @staticmethod
    def format_power(watts: float, unit: str = "auto") -> str:
        """Format power value for display.

        Args:
            watts: Power in watts (absolute value used).
            unit: "auto", "W", or "kW".

        Returns:
            Formatted string like "2.3 kW", "400 W", or "0 W".
        """
        w = abs(watts) if watts else 0

        if unit == "kW":
            return f"{w / 1000:.1f} kW"
        elif unit == "W":
            return f"{int(round(w))} W"
        else:
            # auto
            if w >= 1000:
                return f"{w / 1000:.1f} kW"
            else:
                return f"{int(round(w))} W"

    @staticmethod
    def format_duration(seconds: Optional[float]) -> str:
        """Format duration for display.

        Args:
            seconds: Duration in seconds (EVCC API convention).

        Returns:
            Formatted string: "" if 0/<60s, "45m", "2:44h", "1d 3h".
        """
        if not seconds:
            return ""

        if seconds < 60:
            return ""
        elif seconds < 3600:
            minutes = int(seconds // 60)
            return f"{minutes}m"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}:{minutes:02d}h"
        else:
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            return f"{days}d {hours}h"

    @staticmethod
    def derive_status(lp: Dict[str, Any]) -> str:
        """Derive human-readable charging status from loadpoint state.

        Args:
            lp: Loadpoint dict from EVCC API.

        Returns:
            Status string: "Charging", "Waiting for solar", "Finished",
            "Connected", or "Disconnected".
        """
        connected = lp.get("connected", False)
        enabled = lp.get("enabled", False)
        charging = lp.get("charging", False)
        mode = lp.get("mode", "")

        if charging:
            return "Charging"
        if connected and enabled and not charging and mode in ("pv", "minpv"):
            return "Waiting for solar"
        if connected and enabled and not charging:
            return "Finished"
        if connected and not enabled:
            return "Connected"
        return "Disconnected"

    def transform_energy(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Transform energy/power data from EVCC state.

        Args:
            state: Full EVCC state dict.

        Returns:
            Dict with pv, grid, home power data and tariff info.
        """
        pv_power = state.get("pvPower", 0) or 0

        # Grid power: nested at state["grid"]["power"] (v0.207+),
        # fallback to state["gridPower"] for older EVCC
        grid_obj = state.get("grid", {})
        if isinstance(grid_obj, dict):
            grid_power_raw = grid_obj.get("power", state.get("gridPower", 0)) or 0
        else:
            grid_power_raw = state.get("gridPower", 0) or 0

        home_power = state.get("homePower", 0) or 0

        green_share_raw = state.get("greenShareHome", 0) or 0

        return {
            "pv_power": pv_power,
            "pv_power_formatted": self.format_power(pv_power, self.power_unit),
            "grid_power": abs(grid_power_raw),
            "grid_power_formatted": self.format_power(grid_power_raw, self.power_unit),
            "grid_import": grid_power_raw > 0,
            "home_power": home_power,
            "home_power_formatted": self.format_power(home_power, self.power_unit),
            "green_share_home": round(green_share_raw * 100),
            "tariff_grid": state.get("tariffGrid"),
            "tariff_feedin": state.get("tariffFeedIn"),
            "tariff_price_home": state.get("tariffPriceHome"),
        }

    def transform_battery(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Transform battery data from EVCC state.

        Args:
            state: Full EVCC state dict.

        Returns:
            Dict with battery configuration, SOC, power, and charging status.
        """
        batteries = state.get("battery", [])
        if not isinstance(batteries, list):
            batteries = []

        configured = len(batteries) > 0

        if not configured:
            return {
                "configured": False,
                "soc": 0,
                "power": 0,
                "power_formatted": self.format_power(0, self.power_unit),
                "charging": False,
            }

        total_power = sum(b.get("power", 0) or 0 for b in batteries)
        soc_values = [b.get("soc", 0) or 0 for b in batteries]
        avg_soc = sum(soc_values) / len(soc_values) if soc_values else 0

        return {
            "configured": True,
            "soc": round(avg_soc),
            "power": total_power,
            "power_formatted": self.format_power(total_power, self.power_unit),
            "charging": total_power > 0,
        }

    def transform_loadpoint(self, lp: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a single loadpoint from EVCC state.

        Args:
            lp: Loadpoint dict from EVCC API.

        Returns:
            Dict with all loadpoint fields for the template.
        """
        mode = lp.get("mode", "off")
        charge_power = lp.get("chargePower", 0) or 0
        charged_energy = lp.get("chargedEnergy", 0) or 0

        # Solar percentage: prefer sessionSolarPercentage (already 0-100 range)
        session_solar_pct = lp.get("sessionSolarPercentage")
        if session_solar_pct is None:
            session_solar_pct = 0
        else:
            session_solar_pct = round(session_solar_pct)

        # Session price is a float (total cost for the session)
        session_price_raw = lp.get("sessionPrice")
        session_price = round(session_price_raw, 2) if session_price_raw is not None else None

        return {
            "title": lp.get("title", ""),
            "mode": mode,
            "mode_label": self.MODE_LABELS.get(mode, mode),
            "charging": lp.get("charging", False),
            "connected": lp.get("connected", False),
            "enabled": lp.get("enabled", False),
            "status": self.derive_status(lp),
            "charge_power": charge_power,
            "charge_power_formatted": self.format_power(charge_power, self.power_unit),
            "charged_energy_kwh": round(charged_energy / 1000, 1),
            "charge_duration_formatted": self.format_duration(lp.get("chargeDuration")),
            "charge_remaining_formatted": self.format_duration(lp.get("chargeRemainingDuration")),
            "session_solar_pct": session_solar_pct,
            "session_price": session_price,
            "vehicle_title": lp.get("vehicleTitle") or lp.get("vehicleName"),
            "vehicle_soc": round(lp.get("vehicleSoc", 0) or 0),
            "vehicle_range": lp.get("vehicleRange"),
            "vehicle_connected": lp.get("connected", False),
            "limit_soc": lp.get("effectiveLimitSoc"),
            "plan_active": lp.get("planActive", False),
            "plan_time": lp.get("planTime"),
            "phases_active": lp.get("phasesActive"),
        }

    @staticmethod
    def transform_statistics(state: Dict[str, Any]) -> Dict[str, Any]:
        """Transform statistics from EVCC state.

        Args:
            state: Full EVCC state dict.

        Returns:
            Dict with "30d" and "total" keys, each containing
            charged_kwh, solar_pct, and avg_price.
        """
        stats = state.get("statistics", {})
        result = {}

        for period in ("30d", "total"):
            period_data = stats.get(period, {})
            charged = period_data.get("chargedKWh")
            solar = period_data.get("solarPercentage")
            price = period_data.get("avgPrice")
            result[period] = {
                "charged_kwh": round(charged, 1) if charged is not None else None,
                "solar_pct": round(solar) if solar is not None else None,
                "avg_price": round(price, 2) if price is not None else None,
            }

        return result

    def _get_timezone_abbrev(self) -> str:
        """Get timezone abbreviation from configured timezone."""
        if not self.timezone:
            return "UTC"

        try:
            tz = ZoneInfo(self.timezone)
            now = datetime.now(tz)
            abbrev = now.strftime('%Z')
            return abbrev if abbrev else self.timezone
        except Exception:
            return self.timezone if self.timezone else "UTC"

    def collect(self) -> Dict[str, Any]:
        """Collect all data from EVCC and build the payload.

        Returns:
            Dict with merge_variables for TRMNL.
        """
        logger.info(f"Collecting data from {self.url}")

        state = self._api_request()

        # Timestamps
        now_utc = datetime.now(timezone.utc)
        utc_iso = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')

        if self.timezone:
            tz = ZoneInfo(self.timezone)
            local_now = datetime.now(tz)
            local_formatted = local_now.strftime('%Y-%m-%d %H:%M')
        else:
            local_formatted = datetime.now().strftime('%Y-%m-%d %H:%M')

        tz_abbrev = self._get_timezone_abbrev()

        loadpoints = state.get("loadpoints", [])

        payload = {
            "merge_variables": {
                "site_title": state.get("siteTitle", "EVCC"),
                "last_updated": utc_iso,
                "last_updated_local": local_formatted,
                "timezone": tz_abbrev,
                "currency": state.get("currency", "EUR"),
                "energy": self.transform_energy(state),
                "battery": self.transform_battery(state),
                "loadpoints": [
                    self.transform_loadpoint(lp)
                    for lp in loadpoints[:self.max_loadpoints]
                ],
                "loadpoint_count": len(loadpoints),
                "statistics": self.transform_statistics(state),
            }
        }

        return payload

    def send(self, payload: Dict[str, Any]) -> bool:
        """Send payload to TRMNL webhook.

        Args:
            payload: Full payload dict with merge_variables.

        Returns:
            True if sent successfully, False otherwise.
        """
        payload_json = json.dumps(payload)

        if self.verbose:
            logger.info(f"Payload size: {len(payload_json)} bytes")

        # Dry run or no webhook - print to stdout
        if self.dry_run or not self.webhook:
            print(json.dumps(payload, indent=2))
            return True

        # Send to webhook
        logger.info("Sending data to TRMNL webhook...")
        try:
            response = requests.post(
                self.webhook,
                headers={'Content-Type': 'application/json'},
                data=payload_json,
                timeout=30,
            )
            response.raise_for_status()
            logger.info(f"Successfully sent data (HTTP {response.status_code})")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send data: {e}")
            if self.verbose and hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return False


# --- HTTP serve mode for Terminus/BYOS ---

_serve_data: Dict[str, Dict[str, Any]] = {}
_serve_lock = threading.Lock()


def store_payload(payload: Dict[str, Any]):
    """Cache latest payload for HTTP serving."""
    data = payload.get('merge_variables', payload)
    with _serve_lock:
        _serve_data["evcc"] = data


class DataHandler(BaseHTTPRequestHandler):
    """HTTP handler that serves cached EVCC data as JSON."""

    def do_GET(self):
        path = self.path.rstrip('/')

        if path == '' or path == '/':
            with _serve_lock:
                endpoints = {
                    name: f'/data/{name}' for name in _serve_data
                }
            self._json_response(200, {"endpoints": {"evcc": "/data/evcc"}})
            return

        if path == '/data/evcc':
            with _serve_lock:
                data = _serve_data.get("evcc")
            if data is None:
                self._json_response(404, {"error": "No data collected yet"})
                return
            self._json_response(200, data)
            return

        self.send_response(404)
        self.end_headers()

    def _json_response(self, status: int, body: Any):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        logger.debug(f"HTTP: {args[0]}")


def start_server(host: str, port: int):
    """Start HTTP server in a daemon thread."""
    server = HTTPServer((host, port), DataHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"HTTP server listening on {host}:{port}")
    return server


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def run_collection(collector: EVCCCollector) -> bool:
    """Run a single collection cycle.

    Args:
        collector: The EVCC collector instance.

    Returns:
        True if collection and send succeeded, False otherwise.
    """
    logger.info(f"Starting collection cycle at {datetime.now()}")
    try:
        payload = collector.collect()
        store_payload(payload)
        success = collector.send(payload)
        if success:
            logger.info("Collection complete: success")
        else:
            logger.warning("Collection complete: webhook send failed")
        return success
    except Exception as e:
        logger.error(f"Collection failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='TRMNL EVCC Collector - Collect data from EVCC and send to TRMNL webhook',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # With config file
  %(prog)s --config config.yaml

  # CLI only
  %(prog)s -u http://evcc:7070 -w https://webhook_url

  # Dry run (print JSON, don't send)
  %(prog)s -u http://evcc:7070 --dry-run

  # HTTP serve mode
  %(prog)s --config config.yaml --serve --port 8080
'''
    )

    # Config file
    parser.add_argument('--config', '-C', help='Path to YAML config file')

    # Instance options
    parser.add_argument('-u', '--url', help='EVCC URL (e.g. http://evcc:7070)')
    parser.add_argument('-w', '--webhook', help='TRMNL webhook URL')
    parser.add_argument('-z', '--timezone', default='', help='Timezone (default: from TZ env)')
    parser.add_argument('-i', '--interval', type=int, default=0,
                        help='Collection interval in seconds (0 = run once)')
    parser.add_argument('--max-loadpoints', type=int, default=4,
                        help='Max loadpoints to include (default: 4)')
    parser.add_argument('--power-unit', choices=['W', 'kW', 'auto'], default='auto',
                        help='Power display unit (default: auto)')
    parser.add_argument('--serve', action='store_true', help='Enable HTTP server')
    parser.add_argument('--port', type=int, default=8080, help='HTTP server port (default: 8080)')
    parser.add_argument('--host', default='0.0.0.0', help='HTTP bind address (default: 0.0.0.0)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Debug logging')
    parser.add_argument('--dry-run', action='store_true', help='Print JSON, don\'t send')
    parser.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')

    args = parser.parse_args()

    # Build collector from config or CLI args
    if args.config:
        try:
            config = load_config(args.config)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            sys.exit(1)

        interval = config.get('interval', args.interval)
        evcc_url = config.get('evcc_url')
        if not evcc_url:
            logger.error("Config file must contain 'evcc_url'")
            sys.exit(1)

        collector = EVCCCollector(
            url=evcc_url,
            webhook=config.get('webhook', args.webhook),
            timezone=config.get('timezone', args.timezone),
            max_loadpoints=config.get('max_loadpoints', args.max_loadpoints),
            power_unit=config.get('power_unit', args.power_unit),
            verbose=args.verbose,
            dry_run=args.dry_run,
        )

        serve = args.serve
        serve_config = config.get('serve', {})
        serve = serve or serve_config.get('enabled', False)
        serve_port = serve_config.get('port', args.port)
        serve_host = serve_config.get('host', args.host)
    else:
        if not args.url:
            logger.error("Either --config or --url is required")
            parser.print_help()
            sys.exit(1)

        interval = args.interval
        collector = EVCCCollector(
            url=args.url,
            webhook=args.webhook,
            timezone=args.timezone,
            max_loadpoints=args.max_loadpoints,
            power_unit=args.power_unit,
            verbose=args.verbose,
            dry_run=args.dry_run,
        )

        serve = args.serve
        serve_port = args.port
        serve_host = args.host

    logger.info(f"TRMNL EVCC Collector v{VERSION}")
    logger.info(f"EVCC URL: {collector.url}")

    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info("Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start HTTP server if requested
    if serve:
        start_server(serve_host, serve_port)

    # Run collection
    if interval > 0:
        logger.info(f"Running continuously with {interval}s interval (Ctrl+C to stop)")
        while True:
            run_collection(collector)
            logger.info(f"Sleeping for {interval} seconds...")
            time.sleep(interval)
    else:
        # Single run
        success = run_collection(collector)
        logger.info("Done!")
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
