from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import aiohttp, asyncio, os, json, logging, pytz, sys
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Advanced Logging
class LogBufferHandler(logging.Handler):
    def __init__(self, capacity=200):
        super().__init__()
        self.capacity = capacity
        self.buffer = []
    def emit(self, record):
        msg = f"{datetime.now().strftime('%H:%M:%S')} - {record.levelname} - {self.format(record)}"
        self.buffer.append(msg)
        if len(self.buffer) > self.capacity: self.buffer.pop(0)

log_buffer = LogBufferHandler()
logging.basicConfig(level=logging.INFO, format='%(message)s', handlers=[logging.StreamHandler(sys.stdout), log_buffer])
logger = logging.getLogger("energy-optimiser")

app = FastAPI(docs_url=None, redoc_url=None)
CONFIG_PATH, VERSION = "/data/config.json", "2026.3.38"

DEFAULT_CONFIG = {
    "enabled": False, "market_area": "NL", "strategy": "Maximize Profit",
    "battery_capacity_kwh": 5.0, "battery_min_soc": 20.0, "battery_max_soc": 100.0,
    "charge_threshold_pct": 85, "discharge_threshold_pct": 115, "max_charge_rate_kw": 2.5,
    "update_interval_minutes": 60, "solarman_battery_soc": "sensor.solarman_battery_soc",
    "solarman_prog_times": [f"number.solarman_prog{i}_time" for i in range(1,7)],
    "solarman_prog_socs": [f"number.solarman_prog{i}_soc" for i in range(1,7)],
    "solarman_prog_grid_charges": [f"switch.solarman_prog{i}_grid_charge" for i in range(1,7)],
    "meteoserver_key": "", "meteoserver_location": "Utrecht", "solar_enabled": False,
    "solar_arrays": [{"name": "Dak", "kwp": 4.0, "tilt": 35, "azimuth": 180, "efficiency": 0.85}]
}

class Optimizer:
    def __init__(self):
        self.config = self.load_config()
        self.prices, self.forecast, self.last_update = [], [], None
        self.current_soc, self._session = 50.0, None
        self.api_errors = {"prices": "", "weather": "", "ha": ""}

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f: return {**DEFAULT_CONFIG, **json.load(f)}
            except: pass
        return DEFAULT_CONFIG

    def save_config(self, cfg):
        self.config.update(cfg)
        with open(CONFIG_PATH, "w") as f: json.dump(self.config, f, indent=2)
        logger.info("Configuration updated and stored in /data/config.json")

    async def get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def fetch_data(self):
        session = await self.get_session()
        token, entity = os.getenv("SUPERVISOR_TOKEN"), self.config.get("solarman_battery_soc")
        if token and entity:
            try:
                async with session.get(f"http://supervisor/core/api/states/{entity}", headers={"Authorization": f"Bearer {token}"}) as r:
                    if r.status == 200:
                        data = await r.json()
                        self.current_soc = float(data.get("state", 50.0))
                        self.api_errors["ha"] = "OK"
                    else: self.api_errors["ha"] = f"Error {r.status}"
            except: self.api_errors["ha"] = "Connection Failed"

        try:
            now = datetime.now(pytz.timezone("Europe/Amsterdam"))
            start, end = now.replace(hour=0,min=0,sec=0), now.replace(hour=0,min=0,sec=0) + timedelta(days=2)
            url = f"https://api.energyzero.nl/v1/energyprices?fromDate={start.isoformat()}&toDate={end.isoformat()}&interval=4&usageType=1&inclBtw=true"
            async with session.get(url) as r:
                if r.status == 200:
                    data = await r.json()
                    self.prices = [{"time": p["readingDate"], "price": p["price"]} for p in data.get("Prices", [])]
                    avg = sum(p["price"] for p in self.prices) / len(self.prices) if self.prices else 0
                    self.forecast = [{"time": p["time"], "price": p["price"], "action": "CHARGE" if p["price"] < avg * 0.9 else "IDLE"} for p in self.prices[:24]]
                    self.last_update = datetime.now()
                    self.api_errors["prices"] = "OK"
                else: self.api_errors["prices"] = f"Error {r.status}"
        except: self.api_errors["prices"] = "Fetch Failed"

    async def loop(self):
        while True:
            if self.config.get("enabled"): await self.fetch_data()
            await asyncio.sleep(self.config.get("update_interval_minutes", 60) * 60)

state = Optimizer()

@app.on_event("startup")
async def startup(): asyncio.create_task(state.loop())

@app.get("/api/status")
async def get_status():
    return {"config": state.config, "forecast": state.forecast, "last_update": state.last_update, "current_soc": state.current_soc, "api_errors": state.api_errors, "version": VERSION}

@app.get("/api/logs")
async def get_logs(): return {"logs": log_buffer.buffer}

@app.post("/api/config")
async def update_config(cfg: dict): state.save_config(cfg); return {"ok": True}

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r") as f: return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
