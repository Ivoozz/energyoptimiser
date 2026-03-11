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

# Professional Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("energy-optimiser")

app = FastAPI(docs_url=None, redoc_url=None)

CONFIG_PATH = "/data/config.json"

DEFAULT_CONFIG = {
    "enabled": False,
    "price_provider": "EnergyZero",
    "market_area": "NL",
    "currency": "EUR",
    "strategy": "Maximize Profit",
    "charge_threshold_pct": 85,
    "discharge_threshold_pct": 115,
    "battery_capacity_kwh": 5.0,
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
                    # Migrate old solar settings
                    if "solar_kwp" in data:
                        data["solar_arrays"] = [{"name": "Dak", "kwp": data.pop("solar_kwp"), "tilt": data.pop("solar_tilt", 35), "azimuth": data.pop("solar_azimuth", 180), "efficiency": data.pop("solar_efficiency", 0.85)}]
                    # Migrate nordpool_area to market_area
                    if "nordpool_area" in data:
                        data["market_area"] = data.pop("nordpool_area")
                    # Ensure array lengths for prog settings
                    for key in ["solarman_prog_times", "solarman_prog_socs", "solarman_prog_grid_charges"]:
                        if key not in data or not isinstance(data[key], list) or len(data[key]) < 6:
                            data[key] = DEFAULT_CONFIG[key]
                    return {**DEFAULT_CONFIG, **data}
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
        return DEFAULT_CONFIG

    def save_config(self, new_config: Dict[str, Any]):
        self.config = new_config
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(new_config, f, indent=2)
            logger.info("Config saved.")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def get_current_soc(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        entity_id = self.config.get("solarman_battery_soc")
        if not token or not entity_id: return
        
        url = f"http://supervisor/core/api/states/{entity_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            session = await self.get_session()
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.current_soc = float(data.get("state", 50.0))
                    logger.debug(f"SOC Updated: {self.current_soc}%")
                else:
                    logger.error(f"HA SOC Fetch Error: {resp.status}")
        except Exception as e:
            logger.error(f"HA SOC Connection Error: {e}")

    async def fetch_prices(self):
        logger.info("Fetching EnergyZero prices...")
        now = datetime.now(pytz.UTC)
        start = now.strftime("%Y-%m-%dT00:00:00.000Z")
        end = (now + timedelta(days=1)).strftime("%Y-%m-%dT23:59:59.999Z")
        url = f"https://api.energyzero.nl/v1/energyprices?fromDate={start}&tillDate={end}&interval=4&usageType=1&inclBtw=true"
        
        try:
            session = await self.get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if not data or "Prices" not in data:
                        logger.error(f"EnergyZero API returned invalid data: {data}")
                        return

                    new_prices = []
                    for item in data.get("Prices", []):
                        try:
                            if "readingDate" in item and "price" in item:
                                dt = datetime.fromisoformat(item["readingDate"].replace('Z', '+00:00'))
                                new_prices.append({"timestamp": dt, "value": float(item["price"])})
                        except (ValueError, TypeError) as e:
                            logger.error(f"Error parsing price item {item}: {e}")
                            continue

                    if new_prices:
                        self.prices = new_prices
                        logger.info(f"Loaded {len(self.prices)} price points.")
                    else:
                        logger.warning("No price points loaded from EnergyZero API.")
                else:
                    logger.error(f"EnergyZero API Error: {resp.status} - {await resp.text()}")
        except Exception as e:
            logger.error(f"EnergyZero Connection Error: {e}", exc_info=True)

    async def fetch_weather(self):
        key = self.config.get("meteoserver_key")
        loc = self.config.get("meteoserver_location")
        if not key or not loc: return
        url = f"https://data.meteoserver.nl/api/uurverwachting.php?key={key}&locatie={loc}"
        try:
            session = await self.get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.weather = data.get("data", [])
                    logger.info(f"Weather loaded for {loc}")
                else:
                    logger.error(f"Meteoserver API Error: {resp.status}")
        except Exception as e:
            logger.error(f"Meteoserver Connection Error: {e}")

    def calculate_solar_yield(self, radiation_wm2: float, hour: int) -> float:
        if not self.config.get("solar_enabled"): return 0.0
        total = 0.0
        for array in self.config.get("solar_arrays", []):
            try:
                kwp = float(array.get("kwp", 0.0))
                tilt = math.radians(float(array.get("tilt", 35.0)))
                azimuth_deg = float(array.get("azimuth", 180.0))
                az_factor = math.cos(math.radians(azimuth_deg - 180.0))
                pr = float(array.get("efficiency", 0.85))
                time_factor = max(0.0, 1.0 - abs(hour - 12) / 8.0)
                total += (radiation_wm2 / 1000.0) * kwp * pr * math.cos(tilt) * time_factor * max(0.1, az_factor)
            except Exception as e:
                logger.error(f"Error calculating solar yield for array {array.get('name', 'unknown')}: {e}", exc_info=True)
                continue
        return max(0.0, total)

    def calculate_forecast(self):
        if not self.prices: return
        
        avg_p = sum(p["value"] for p in self.prices) / len(self.prices)
        strategy = self.config.get("strategy", "Maximize Profit")
        charge_t = float(self.config.get("charge_threshold_pct", 85)) / 100.0
        discharge_t = float(self.config.get("discharge_threshold_pct", 115)) / 100.0
        battery_cap = float(self.config.get("battery_capacity_kwh", 5.0))
        
        tz = pytz.timezone(self.timezone)
        weather_map = {w['tijd'].split(' ')[1][:2]: w for w in self.weather if 'tijd' in w}
        
        total_expected_solar_kwh = 0.0
        temp_data = []
        now = datetime.now(pytz.UTC)
        relevant_prices = [p for p in self.prices if p["timestamp"] >= now - timedelta(hours=1)][:24]

        for p in relevant_prices:
            lt = p["timestamp"].astimezone(tz)
            h_str = f"{lt.hour:02d}"
            rad = float(weather_map.get(h_str, {}).get('gr', 0))
            solar_kw = self.calculate_solar_yield(rad, lt.hour)
            total_expected_solar_kwh += solar_kw
            temp_data.append({"lt": lt, "price": p["value"], "solar_kw": solar_kw, "h_str": h_str})

        # Decision Logic
        energy_needed = battery_cap * (1.0 - (self.current_soc / 100.0))
        will_fill_from_sun = (total_expected_solar_kwh > (energy_needed * 1.1))
        
        new_forecast = []
        for item in temp_data:
            price, solar_kw = item["price"], item["solar_kw"]
            action, grid_charge = "IDLE", "off"
            
            if strategy == "Maximize Profit":
                if price <= (avg_p * charge_t):
                    if not will_fill_from_sun: action, grid_charge = "CHARGE", "on"
                    else: action = "WAIT FOR SUN"
                elif price >= (avg_p * discharge_t): action = "DISCHARGE"
            elif strategy == "Maximize Self-Consumption":
                if self.current_soc < 15 and price <= avg_p: action, grid_charge = "CHARGE", "on"
            elif strategy == "Zero on the Meter":
                if price < 0: action, grid_charge = "CHARGE (NEG)", "on"
                else: action = "AUTONOMOUS"
            
            new_forecast.append({
                "time": item["lt"].isoformat(),
                "hour": item["lt"].hour,
                "price": round(price, 4),
                "weather": weather_map.get(item["h_str"], {}).get('vvoorsp', 'N/A'),
                "solar_yield": round(solar_kw, 2),
                "action": action,
                "grid_charge": grid_charge
            })
        
        self.forecast = new_forecast
        self.last_update = datetime.now()
        self.map_slots()
        gc.collect()

    def map_slots(self):
        if not self.forecast: return
        slots = []
        curr_act, curr_grid, start_h = self.forecast[0]["action"], self.forecast[0]["grid_charge"], self.forecast[0]["hour"]
        for h in self.forecast[1:]:
            if h["action"] != curr_act or h["grid_charge"] != curr_grid:
                slots.append({"start": start_h, "action": curr_act, "grid_charge": curr_grid})
                curr_act, curr_grid, start_h = h["action"], h["grid_charge"], h["hour"]
        slots.append({"start": start_h, "action": curr_act, "grid_charge": curr_grid})
        while len(slots) > 6: slots.pop()
        while len(slots) < 6: slots.append({"start": (slots[-1]["start"]+1)%24, "action": "IDLE", "grid_charge": "off"})
        self.inverter_slots = slots

    async def apply_to_ha(self, dry_run=False):
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token or not self.inverter_slots: return
        if not self.config.get("enabled") and not dry_run: return
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        base_url = "http://supervisor/core/api/services"
        session = await self.get_session()
        
        logger.info(f"Syncing {len(self.inverter_slots)} slots to HA (DryRun={dry_run})")
        for i in range(min(len(self.inverter_slots), 6)):
            slot = self.inverter_slots[i]
            try:
                t_val = int(slot["start"] * 100)
                soc = 100 if (slot["action"] == "CHARGE" or slot["action"] == "AUTONOMOUS") else 20
                svc = "switch/turn_on" if slot["grid_charge"] == "on" else "switch/turn_off"
                
                if not dry_run:
                    await session.post(f"{base_url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_times"][i], "value": t_val})
                    await session.post(f"{base_url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_socs"][i], "value": soc})
                    await session.post(f"{base_url}/{svc}", headers=headers, json={"entity_id": self.config["solarman_prog_grid_charges"][i]})
                else:
                    logger.info(f"DRY RUN: Slot {i+1} -> Time: {t_val}, SOC: {soc}, Grid: {svc}")
            except Exception as e:
                logger.error(f"Sync error slot {i+1}: {e}")

    async def run_loop(self):
        logger.info("Main Optimization Loop Started.")
        while True:
            try:
                if self.config.get("enabled"):
                    await self.get_current_soc()
                    await self.fetch_prices()
                    await self.fetch_weather()
                    self.calculate_forecast()
                    await self.apply_to_ha()
                
                wait = max(1, self.config.get("update_interval_minutes", 60))
                logger.debug(f"Loop cycle done. Sleeping {wait} min.")
                await asyncio.sleep(wait * 60)
            except Exception as e:
                logger.critical(f"Loop Crash: {e}", exc_info=True)
                await asyncio.sleep(60)

state = Optimizer()

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(state.run_loop())

@app.on_event("shutdown")
async def on_shutdown():
    if state._session: await state._session.close()

@app.get("/api/status")
async def get_status():
    return {
        "config": state.config,
        "forecast": state.forecast,
        "inverter_slots": state.inverter_slots,
        "last_update": state.last_update.isoformat() if state.last_update else None,
        "current_soc": state.current_soc
    }

@app.post("/api/config")
async def save_config(new_config: dict):
    state.save_config(new_config)
    return JSONResponse(status_code=200, content={"status": "ok"})

@app.post("/api/test_run")
async def test_run():
    await state.get_current_soc()
    await state.fetch_prices()
    await state.fetch_weather()
    state.calculate_forecast()
    await state.apply_to_ha(dry_run=True)
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    try:
        with open("static/index.html", "r") as f: return f.read()
    except Exception as e:
        return HTMLResponse(content=f"UI Error: {e}", status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=1, access_log=False)
