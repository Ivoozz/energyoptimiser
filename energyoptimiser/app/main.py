from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
import aiohttp
import asyncio
import os
import json
import logging
import sys
import math
import gc
from datetime import datetime, time, timedelta
import pytz
from typing import Optional, List, Dict, Any

# Professional Logging with File and Stream handler
LOG_FILE = "/data/energy-optimiser.log"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

class LogBufferHandler(logging.Handler):
    def __init__(self, capacity=100):
        super().__init__()
        self.capacity = capacity
        self.buffer = []

    def emit(self, record):
        msg = self.format(record)
        self.buffer.append(msg)
        if len(self.buffer) > self.capacity:
            self.buffer.pop(0)

log_buffer = LogBufferHandler()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
        log_buffer
    ]
)
logger = logging.getLogger("energy-optimiser")

app = FastAPI(docs_url=None, redoc_url=None)

CONFIG_PATH = "/data/config.json"
VERSION = "v2026.3.32"

DEFAULT_CONFIG = {
    "enabled": False,
    "onboarding_completed": False,
    "market_area": "NL",
    "currency": "EUR",
    "strategy": "Maximize Profit",
    "charge_threshold_pct": 85,
    "discharge_threshold_pct": 115,
    "battery_capacity_kwh": 5.0,
    "battery_min_soc": 20.0,
    "battery_max_soc": 100.0,
    "max_charge_rate_kw": 2.5,
    "update_interval_minutes": 60,
    "solarman_battery_soc": "sensor.solarman_battery_soc",
    "solarman_prog_times": ["number.solarman_prog1_time"] * 6,
    "solarman_prog_socs": ["number.solarman_prog1_soc"] * 6,
    "solarman_prog_grid_charges": ["switch.solarman_prog1_grid_charge"] * 6,
    "meteoserver_key": "",
    "meteoserver_location": "Utrecht",
    "solar_enabled": False,
    "solar_arrays": [{"name": "Dak", "kwp": 4.0, "tilt": 35, "azimuth": 180, "efficiency": 0.85}]
}

@app.middleware("http")
async def ingress_middleware(request: Request, call_next):
    ingress_path = request.headers.get("X-Ingress-Path")
    if ingress_path:
        request.scope["root_path"] = ingress_path.rstrip("/")
    return await call_next(request)

class Optimizer:
    def __init__(self):
        self.config = self.load_config()
        self.prices = []
        self.weather = []
        self.forecast = []
        self.inverter_slots = []
        self.last_update = None
        self.timezone = os.getenv("TZ", "Europe/Amsterdam")
        self.current_soc = 50.0
        self._session: Optional[aiohttp.ClientSession] = None

    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    data = json.load(f)
                    return {**DEFAULT_CONFIG, **data}
            except Exception as e:
                logger.error(f"Config load failed: {e}")
        return DEFAULT_CONFIG

    def save_config(self, new_config: Dict[str, Any]):
        self.config = new_config
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(new_config, f, indent=2)
            logger.info("Configuration saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def fetch_soc_from_ha(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        entity_id = self.config.get("solarman_battery_soc")
        if not token or not entity_id: return
        url = f"http://supervisor/core/api/states/{entity_id}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            session = await self.get_session()
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.current_soc = float(data.get("state", 50.0))
        except Exception as e:
            logger.error(f"HA SOC Error: {e}")

    async def fetch_prices(self):
        """Fetches electricity prices from EasyEnergy (Alternative to EnergyZero)."""
        logger.info("Fetching EasyEnergy prices...")
        now = datetime.now(pytz.UTC)
        start = now.strftime("%Y-%m-%dT00:00:00")
        url = f"https://mijn.easyenergy.com/nl/api/tariff/getapxtariffs?startTimestamp={start}&endTimestamp={start}" # Simplified for now
        
        # Real logic: EasyEnergy returns a list of tariffs
        try:
            session = await self.get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    new_prices = []
                    for item in data:
                        dt = datetime.fromisoformat(item["Timestamp"].replace('Z', '+00:00'))
                        new_prices.append({"timestamp": dt, "value": float(item["TariffUsage"])})
                    self.prices = sorted(new_prices, key=lambda x: x["timestamp"])
                    logger.info(f"Fetched {len(self.prices)} prices.")
                else:
                    logger.error(f"Price API Error: {resp.status}")
        except Exception as e:
            logger.error(f"Price Connection Error: {e}")

    async def fetch_weather(self):
        key = self.config.get("meteoserver_key")
        loc = self.config.get("meteoserver_location")
        if not key or not loc: return
        url = f"https://data.meteoserver.nl/api/uurverwachting.php?key={key}&locatie={loc}"
        try:
            session = await self.get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    data = json.loads(text)
                    self.weather = data.get("data", [])
                    logger.info(f"Weather updated for {loc}")
        except Exception as e:
            logger.error(f"Weather error: {e}")

    def calculate_forecast(self):
        if not self.prices: return
        avg_p = sum(p["value"] for p in self.prices) / len(self.prices)
        tz = pytz.timezone(self.timezone)
        new_forecast = []
        for p in self.prices[:24]:
            lt = p["timestamp"].astimezone(tz)
            action = "CHARGE" if p["value"] < avg_p * 0.8 else "IDLE"
            new_forecast.append({
                "time": lt.isoformat(),
                "price": round(p["value"], 4),
                "action": action,
                "grid_charge": "on" if action == "CHARGE" else "off"
            })
        self.forecast = new_forecast
        self.last_update = datetime.now()

    async def apply_to_ha(self, dry_run=False):
        if not self.forecast or not self.config.get("enabled") and not dry_run: return
        logger.info(f"Syncing to HA... DryRun: {dry_run}")
        # Simplified sync logic
        pass

    async def loop(self):
        while True:
            if self.config.get("enabled"):
                await self.fetch_soc_from_ha()
                await self.fetch_prices()
                await self.fetch_weather()
                self.calculate_forecast()
                await self.apply_to_ha()
            await asyncio.sleep(self.config.get("update_interval_minutes", 60) * 60)

state = Optimizer()

@app.on_event("startup")
async def startup():
    asyncio.create_task(state.loop())

@app.get("/api/status")
async def get_status():
    return {
        "config": state.config,
        "forecast": state.forecast,
        "last_update": state.last_update.isoformat() if state.last_update else None,
        "current_soc": state.current_soc
    }

@app.get("/api/logs")
async def get_logs():
    return {"logs": log_buffer.buffer}

@app.post("/api/config")
async def update_config(new_config: dict):
    state.save_config(new_config)
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("static/index.html", "r") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
