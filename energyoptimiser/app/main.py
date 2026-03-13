from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import aiohttp, asyncio, os, json, logging, pytz
from datetime import datetime, timedelta
from typing import Dict, Any

# Basis Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("energy-optimiser")
app = FastAPI(docs_url=None, redoc_url=None)

CONFIG_PATH, VERSION = "/data/config.json", "2026.3.34"
DEFAULT_CONFIG = {
    "enabled": False, "market_area": "NL", "battery_capacity_kwh": 5.0, "update_interval_minutes": 60,
    "solarman_battery_soc": "sensor.solarman_battery_soc",
    "solarman_prog_times": [f"number.solarman_prog{i}_time" for i in range(1,7)],
    "solarman_prog_socs": [f"number.solarman_prog{i}_soc" for i in range(1,7)],
    "solarman_prog_grid_charges": [f"switch.solarman_prog{i}_grid_charge" for i in range(1,7)],
    "meteoserver_key": "", "meteoserver_location": "Utrecht"
}

class Optimizer:
    def __init__(self):
        self.config = self.load_config()
        self.prices, self.forecast, self.last_update = [], [], None
        self.current_soc, self._session = 50.0, None

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f: return {**DEFAULT_CONFIG, **json.load(f)}
        return DEFAULT_CONFIG

    def save_config(self, new_config):
        self.config.update(new_config)
        with open(CONFIG_PATH, "w") as f: json.dump(self.config, f, indent=2)
        logger.info("Config saved.")

    async def get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def fetch_data(self):
        session = await self.get_session()
        # Fetch SOC
        token, entity = os.getenv("SUPERVISOR_TOKEN"), self.config.get("solarman_battery_soc")
        if token and entity:
            async with session.get(f"http://supervisor/core/api/states/{entity}", headers={"Authorization": f"Bearer {token}"}) as r:
                if r.status == 200: 
                    data = await r.json()
                    try: self.current_soc = float(data.get("state", 50.0))
                    except: self.current_soc = 50.0
        
        # Fetch EnergyZero Prices
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
                logger.info("Data sync complete.")

    async def run(self):
        while True:
            if self.config.get("enabled"): await self.fetch_data()
            await asyncio.sleep(self.config.get("update_interval_minutes", 60) * 60)

state = Optimizer()

@app.on_event("startup")
async def startup(): asyncio.create_task(state.run())

@app.get("/api/status")
async def status(): return {"config": state.config, "forecast": state.forecast, "last_update": state.last_update, "current_soc": state.current_soc}

@app.post("/api/config")
async def update_cfg(cfg: dict): state.save_config(cfg); return {"ok": True}

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r") as f: return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
