from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import aiohttp, asyncio, os, json, logging, pytz, sys
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Advanced Logging with Buffer
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
CONFIG_PATH, VERSION = "/data/config.json", "2026.3.40"

DEFAULT_CONFIG = {
    "enabled": False, "market_area": "NL", "strategy": "Hoogste Verdienen",
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
        logger.info("Instellingen opgeslagen.")

    async def get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def write_to_ha(self, entity_id: str, value: Any):
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token or not entity_id or "not_set" in entity_id: return
        domain = entity_id.split(".")[0]
        service = "set_value" if domain == "number" else ("turn_on" if value in [True, "on", "ON"] else "turn_off")
        url = f"http://supervisor/core/api/services/{domain}/{service}"
        data = {"entity_id": entity_id}
        if domain == "number": data["value"] = value
        
        try:
            session = await self.get_session()
            async with session.post(url, headers={"Authorization": f"Bearer {token}"}, json=data) as r:
                if r.status != 200: logger.error(f"HA Write Error {entity_id}: {r.status}")
        except Exception as e: logger.error(f"HA Connection Error: {e}")

    async def fetch_data(self):
        session = await self.get_session()
        # Get SOC
        token, entity = os.getenv("SUPERVISOR_TOKEN"), self.config.get("solarman_battery_soc")
        if token and entity:
            try:
                async with session.get(f"http://supervisor/core/api/states/{entity}", headers={"Authorization": f"Bearer {token}"}) as r:
                    if r.status == 200:
                        data = await r.json()
                        self.current_soc = float(data.get("state", 50.0))
                        self.api_errors["ha"] = "OK"
            except: self.api_errors["ha"] = "Error"

        # Get Prices
        try:
            now = datetime.now(pytz.timezone("Europe/Amsterdam"))
            start, end = now.replace(hour=0,min=0,sec=0), now.replace(hour=0,min=0,sec=0) + timedelta(days=2)
            url = f"https://api.energyzero.nl/v1/energyprices?fromDate={start.isoformat()}&toDate={end.isoformat()}&interval=4&usageType=1&inclBtw=true"
            async with session.get(url) as r:
                if r.status == 200:
                    data = await r.json()
                    raw_prices = [{"time": p["readingDate"], "price": float(p["price"])} for p in data.get("Prices", [])]
                    self.prices = sorted(raw_prices, key=lambda x: x["time"])
                    self.api_errors["prices"] = "OK"
                    self.optimize()
        except: self.api_errors["prices"] = "Error"

    def optimize(self):
        if not self.prices: return
        strategy = self.config.get("strategy", "Hoogste Verdienen")
        logger.info(f"Start optimalisatie via strategie: {strategy}")
        
        sorted_prices = sorted(self.prices[:24], key=lambda x: x["price"])
        cheap_hours = [p["time"] for p in sorted_prices[:6]]
        expensive_hours = [p["time"] for p in sorted_prices[-6:]]
        
        slots = []
        if strategy == "Hoogste Verdienen":
            # Arbitrage: Volledig laden bij goedkoop, ontladen bij duur
            for i in range(6):
                time_dt = datetime.fromisoformat(self.prices[i*4]["time"].replace("Z", "+00:00"))
                is_cheap = self.prices[i*4]["time"] in cheap_hours
                slots.append({
                    "time": time_dt.strftime("%H:%M"),
                    "soc": 100 if is_cheap else self.config["battery_min_soc"],
                    "grid": "on" if is_cheap else "off"
                })
        elif strategy == "Hoogst eigen gebruik":
            # Solar focus: Accu leegmaken voor de zon komt
            for i in range(6):
                hour = i * 4
                is_morning = 4 <= hour <= 10
                slots.append({
                    "time": f"{hour:02d}:00",
                    "soc": 20 if is_morning else 100,
                    "grid": "off"
                })
        else: # 0 op de meter
            for i in range(6):
                slots.append({"time": f"{i*4:02d}:00", "soc": 50, "grid": "off"})

        self.forecast = [{"time": s["time"], "price": 0, "action": "CHARGE" if s["grid"]=="on" else "IDLE"} for s in slots]
        asyncio.create_task(self.apply_to_inverter(slots))

    async def apply_to_inverter(self, slots):
        logger.info("Instellingen naar omvormer pushen...")
        for i, slot in enumerate(slots[:6]):
            await self.write_to_ha(self.config["solarman_prog_times"][i], slot["time"])
            await self.write_to_ha(self.config["solarman_prog_socs"][i], slot["soc"])
            await self.write_to_ha(self.config["solarman_prog_grid_charges"][i], slot["grid"])
        logger.info("Inverter succesvol bijgewerkt.")

    async def loop(self):
        while True:
            if self.config.get("enabled"): await self.fetch_data()
            await asyncio.sleep(self.config.get("update_interval_minutes", 60) * 60)

state = Optimizer()

@app.on_event("startup")
async def startup(): asyncio.create_task(state.loop())

@app.get("/api/status")
async def status(): return {"config": state.config, "forecast": state.forecast, "last_update": datetime.now(), "current_soc": state.current_soc, "api_errors": state.api_errors, "version": VERSION}

@app.get("/api/logs")
async def get_logs(): return {"logs": log_buffer.buffer}

@app.post("/api/testrun")
async def test(): await state.fetch_data(); return {"ok": True}

@app.post("/api/config")
async def update_cfg(cfg: dict): state.save_config(cfg); return {"ok": True}

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r") as f: return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
