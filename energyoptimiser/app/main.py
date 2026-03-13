from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import aiohttp, asyncio, os, json, logging, pytz, sys
from datetime import datetime, timedelta
from typing import Dict, Any, List
from nordpool import elspot

# Expliciete Logging Buffer Fix
class LogBufferHandler(logging.Handler):
    def __init__(self, capacity=200):
        super().__init__()
        self.capacity = capacity
        self.buffer = []
    def emit(self, record):
        try:
            msg = f"{datetime.now().strftime('%H:%M:%S')} - {record.levelname} - {self.format(record)}"
            self.buffer.append(msg)
            if len(self.buffer) > self.capacity: self.buffer.pop(0)
        except Exception: pass

log_buffer = LogBufferHandler()
formatter = logging.Formatter('%(message)s')
log_buffer.setFormatter(formatter)

logger = logging.getLogger("energy-optimiser")
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.addHandler(log_buffer)
# Voorkom dat logs dubbel verschijnen of worden onderdrukt
logger.propagate = False

app = FastAPI(docs_url=None, redoc_url=None)
CONFIG_PATH, VERSION = "/data/config.json", "2026.3.41"

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
        self.api_errors = {"prices": "Nordpool Standby", "weather": "", "ha": ""}

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f: return {**DEFAULT_CONFIG, **json.load(f)}
            except: pass
        return DEFAULT_CONFIG

    def save_config(self, cfg):
        self.config.update(cfg)
        with open(CONFIG_PATH, "w") as f: json.dump(self.config, f, indent=2)
        logger.info("Configuratie opgeslagen en gesynchroniseerd.")

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
                if r.status != 200: logger.error(f"Fout bij schrijven naar HA ({entity_id}): {r.status}")
        except Exception as e: logger.error(f"HA Verbindingsfout: {e}")

    async def fetch_data(self):
        logger.info("Verversen van systeemdata via Nordpool...")
        session = await self.get_session()
        
        # SOC ophalen
        token, entity = os.getenv("SUPERVISOR_TOKEN"), self.config.get("solarman_battery_soc")
        if token and entity:
            try:
                async with session.get(f"http://supervisor/core/api/states/{entity}", headers={"Authorization": f"Bearer {token}"}) as r:
                    if r.status == 200:
                        data = await r.json()
                        self.current_soc = float(data.get("state", 50.0))
                        self.api_errors["ha"] = "OK"
                        logger.info(f"Huidige batterij SOC: {self.current_soc}%")
            except: self.api_errors["ha"] = "HA Offline"

        # Nordpool Prijzen ophalen
        try:
            prices_elspot = elspot.Prices(currency='EUR')
            # Fetch prices for NL region (Nordpool uses region identifiers)
            # Regio NL is onderdeel van de spot prijzen
            data = prices_elspot.hourly(areas=['NL'])
            raw_prices = []
            for entry in data['areas']['NL']['values']:
                raw_prices.append({
                    "time": entry['start'].isoformat(),
                    "price": float(entry['value']) / 1000 # Omrekenen naar €/kWh
                })
            self.prices = sorted(raw_prices, key=lambda x: x["time"])
            self.api_errors["prices"] = "OK"
            logger.info(f"Nordpool prijzen succesvol opgehaald voor regio NL ({len(self.prices)} data-punten).")
            self.optimize()
        except Exception as e:
            logger.error(f"Nordpool API Fout: {e}")
            self.api_errors["prices"] = f"Nordpool Fout: {str(e)}"

    def optimize(self):
        if not self.prices: return
        strategy = self.config.get("strategy", "Hoogste Verdienen")
        logger.info(f"Start optimalisatie-cyclus. Gekozen strategie: {strategy}")
        
        sorted_prices = sorted(self.prices[:24], key=lambda x: x["price"])
        cheap_hours = [p["time"] for p in sorted_prices[:6]]
        
        slots = []
        if strategy == "Hoogste Verdienen":
            for i in range(6):
                idx = i * 4 if i * 4 < len(self.prices) else len(self.prices) - 1
                time_dt = datetime.fromisoformat(self.prices[idx]["time"].replace("Z", "+00:00"))
                is_cheap = self.prices[idx]["time"] in cheap_hours
                slots.append({
                    "time": time_dt.strftime("%H:%M"),
                    "soc": 100 if is_cheap else self.config.get("battery_min_soc", 20),
                    "grid": "on" if is_cheap else "off"
                })
        elif strategy == "Hoogst eigen gebruik":
            for i in range(6):
                hour = i * 4
                slots.append({
                    "time": f"{hour:02d}:00",
                    "soc": 20 if 4 <= hour <= 10 else 100,
                    "grid": "off"
                })
        else: # 0 op de meter
            for i in range(6):
                slots.append({"time": f"{i*4:02d}:00", "soc": 50, "grid": "off"})

        self.forecast = [{"time": s["time"], "price": 0, "action": "CHARGE" if s["grid"]=="on" else "IDLE"} for s in slots]
        self.last_update = datetime.now()
        asyncio.create_task(self.apply_to_inverter(slots))

    async def apply_to_inverter(self, slots):
        logger.info("Nieuwe programma-slots naar de omvormer sturen...")
        for i, slot in enumerate(slots[:6]):
            await self.write_to_ha(self.config["solarman_prog_times"][i], slot["time"])
            await self.write_to_ha(self.config["solarman_prog_socs"][i], slot["soc"])
            await self.write_to_ha(self.config["solarman_prog_grid_charges"][i], slot["grid"])
        logger.info("Optimalisatie succesvol toegepast op HA entiteiten.")

    async def loop(self):
        while True:
            if self.config.get("enabled"): await self.fetch_data()
            await asyncio.sleep(self.config.get("update_interval_minutes", 60) * 60)

state = Optimizer()

@app.on_event("startup")
async def startup():
    logger.info(f"EnergyOptimiser Engine {VERSION} wordt opgestart...")
    asyncio.create_task(state.loop())

@app.get("/api/status")
async def status():
    return {
        "config": state.config, "forecast": state.forecast, 
        "last_update": state.last_update, "current_soc": state.current_soc, 
        "api_errors": state.api_errors, "version": VERSION
    }

@app.get("/api/logs")
async def get_logs():
    return {"logs": log_buffer.buffer}

@app.post("/api/testrun")
async def test():
    logger.info("Handmatige testrun geactiveerd via UI.")
    await state.fetch_data()
    return {"status": "ok"}

@app.post("/api/config")
async def update_cfg(cfg: dict):
    state.save_config(cfg)
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r") as f: return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
