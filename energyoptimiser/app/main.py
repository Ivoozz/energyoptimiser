from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pynordpool import NordPoolClient, Currency
import aiohttp
import asyncio
import os
import json
import logging
import requests
import sys
import math
import gc
from datetime import datetime, time, timedelta
import pytz
from typing import Optional, List, Dict

# Professional Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("energy-optimiser")

app = FastAPI(docs_url=None, redoc_url=None)

CONFIG_PATH = "/data/config.json"

DEFAULT_CONFIG = {
    "enabled": False,
    "nordpool_area": "NL",
    "currency": "EUR",
    "strategy": "Maximize Profit",
    "charge_threshold_pct": 85,
    "discharge_threshold_pct": 115,
    "battery_capacity_kwh": 5.0,
    "max_charge_rate_kw": 2.5,
    "update_interval_minutes": 60,
    "solarman_battery_soc": "sensor.solarman_battery_soc",
    "solarman_prog_times": [
        "number.solarman_prog1_time", "number.solarman_prog2_time", "number.solarman_prog3_time",
        "number.solarman_prog4_time", "number.solarman_prog5_time", "number.solarman_prog6_time"
    ],
    "solarman_prog_socs": [
        "number.solarman_prog1_soc", "number.solarman_prog2_soc", "number.solarman_prog3_soc",
        "number.solarman_prog4_soc", "number.solarman_prog5_soc", "number.solarman_prog6_soc"
    ],
    "solarman_prog_grid_charges": [
        "switch.solarman_prog1_grid_charge", "switch.solarman_prog2_grid_charge", "switch.solarman_prog3_grid_charge",
        "switch.solarman_prog4_grid_charge", "switch.solarman_prog5_grid_charge", "switch.solarman_prog6_grid_charge"
    ],
    "meteoserver_key": "",
    "meteoserver_location": "Utrecht",
    "solar_enabled": False,
    "solar_arrays": [
        {"name": "Zuid-dak", "kwp": 4.0, "tilt": 35, "azimuth": 180, "efficiency": 0.85}
    ]
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
        self.session: Optional[aiohttp.ClientSession] = None

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    data = json.load(f)
                    return {**DEFAULT_CONFIG, **data}
            except Exception as e:
                logger.error(f"Config load failed: {e}")
        return DEFAULT_CONFIG

    def save_config(self, new_config):
        self.config = new_config
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(new_config, f, indent=2)
        except Exception as e:
            logger.error(f"Config save failed: {e}")

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_current_soc(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        entity_id = self.config.get("solarman_battery_soc")
        if not token or not entity_id: return
        headers = {"Authorization": f"Bearer {token}"}
        url = f"http://supervisor/core/api/states/{entity_id}"
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                self.current_soc = float(r.json().get("state", 50.0))
        except: pass

    async def fetch_prices(self):
        try:
            session = await self.get_session()
            client = NordPoolClient(session)
            area = self.config.get("nordpool_area", "NL")
            curr = getattr(Currency, self.config.get("currency", "EUR"), Currency.EUR)
            self.prices = await client.async_get_delivery_period_prices(currency=curr, area=area)
        except Exception as e:
            logger.error(f"Nordpool Error: {e}")

    async def fetch_weather(self):
        key = self.config.get("meteoserver_key")
        loc = self.config.get("meteoserver_location")
        if not key: return
        url = f"https://data.meteoserver.nl/api/uurverwachting.php?key={key}&locatie={loc}"
        try:
            session = await self.get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self.weather = data.get("data", [])
        except Exception as e:
            logger.error(f"Weather Error: {e}")

    def calculate_solar_yield(self, radiation_wm2, hour):
        if not self.config.get("solar_enabled"): return 0
        total_yield = 0
        for array in self.config.get("solar_arrays", []):
            kwp = array.get("kwp", 0)
            tilt = math.radians(array.get("tilt", 35))
            azimuth_factor = math.cos(math.radians(array.get("azimuth", 180) - 180))
            pr = array.get("efficiency", 0.85)
            time_factor = max(0, 1 - abs(hour - 12) / 8) 
            total_yield += (radiation_wm2 / 1000.0) * kwp * pr * math.cos(tilt) * time_factor * max(0.1, azimuth_factor)
        return max(0, total_yield)

    def calculate_forecast(self):
        if not self.prices: return
        
        avg_p = sum(p.value for p in self.prices) / len(self.prices)
        strategy = self.config.get("strategy", "Maximize Profit")
        charge_t = self.config.get("charge_threshold_pct", 85) / 100.0
        discharge_t = self.config.get("discharge_threshold_pct", 115) / 100.0
        battery_cap = self.config.get("battery_capacity_kwh", 5.0)
        
        tz = pytz.timezone(self.timezone)
        weather_map = {w['tijd'].split(' ')[1][:2]: w for w in self.weather} if self.weather else {}
        
        total_expected_solar_kwh = 0
        temp_data = []
        for p in self.prices[:24]:
            lt = p.timestamp.astimezone(tz)
            h_str = f"{lt.hour:02d}"
            rad = float(weather_map.get(h_str, {}).get('gr', 0)) if h_str in weather_map else 0
            solar_kw = self.calculate_solar_yield(rad, lt.hour)
            total_expected_solar_kwh += solar_kw
            temp_data.append({"lt": lt, "price": p.value, "solar_kw": solar_kw, "h_str": h_str})

        energy_needed = battery_cap * (1 - self.current_soc/100.0)
        will_fill_from_sun = (total_expected_solar_kwh > (energy_needed * 1.1))
        
        new_forecast = []
        for item in temp_data:
            lt, price, solar_kw = item["lt"], item["price"], item["solar_kw"]
            action = "IDLE"
            grid_charge = "off"
            
            if strategy == "Maximize Profit":
                if price <= (avg_p * charge_t):
                    if not will_fill_from_sun:
                        action = "CHARGE"
                        grid_charge = "on"
                    else:
                        action = "WAIT FOR SUN"
                elif price >= (avg_p * discharge_t):
                    action = "DISCHARGE"
            
            elif strategy == "Maximize Self-Consumption":
                # Only charge from grid if critically low AND price is below average
                if self.current_soc < 15 and price <= avg_p:
                    action = "CHARGE"
                    grid_charge = "on"
                else:
                    action = "IDLE (SOLAR ONLY)"
            
            elif strategy == "Zero on the Meter":
                # Absolute minimum grid usage. 
                # Never charge from grid unless price is negative (paying to take energy)
                if price < 0:
                    action = "CHARGE (NEG PRICE)"
                    grid_charge = "on"
                # Never force discharge, let the inverter handle house load from battery naturally
                else:
                    action = "AUTONOMOUS"
                    grid_charge = "off"
            
            new_forecast.append({
                "time": lt.isoformat(),
                "hour": lt.hour,
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
        curr_act = self.forecast[0]["action"]
        curr_grid = self.forecast[0]["grid_charge"]
        start_h = self.forecast[0]["hour"]
        
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
        for i in range(min(len(self.inverter_slots), 6)):
            slot = self.inverter_slots[i]
            try:
                t_val = slot["start"] * 100
                # Default logic: if action is CHARGE or strategy is Self-Consumption/Net-Zero, we allow 100% capacity
                # If action is DISCHARGE, we set a low SOC target to allow discharging
                soc = 100 if (slot["action"] == "CHARGE" or slot["action"] == "AUTONOMOUS") else 20
                svc = "switch/turn_on" if slot["grid_charge"] == "on" else "switch/turn_off"
                
                if not dry_run:
                    requests.post(f"{base_url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_times"][i], "value": t_val}, timeout=10)
                    requests.post(f"{base_url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_socs"][i], "value": soc}, timeout=10)
                    requests.post(f"{base_url}/{svc}", headers=headers, json={"entity_id": self.config["solarman_prog_grid_charges"][i]}, timeout=10)
            except: pass

    async def run_loop(self):
        while True:
            try:
                if self.config.get("enabled"):
                    await self.get_current_soc()
                    await self.fetch_prices()
                    await self.fetch_weather()
                    self.calculate_forecast()
                    await self.apply_to_ha()
                await asyncio.sleep(self.config.get("update_interval_minutes", 60) * 60)
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(60)

state = Optimizer()

@app.on_event("startup")
async def on_startup(): asyncio.create_task(state.run_loop())

@app.on_event("shutdown")
async def on_shutdown():
    if state.session:
        await state.session.close()

@app.get("/api/status")
async def get_status():
    return {
        "config": state.config,
        "forecast": state.forecast,
        "inverter_slots": state.inverter_slots,
        "last_update": state.last_update.isoformat() if state.last_update else None,
        "timezone": state.timezone,
        "current_soc": state.current_soc
    }

@app.post("/api/config")
async def save_config(new_config: dict):
    state.save_config(new_config)
    return {"status": "ok"}

@app.post("/api/test_run")
async def test_run():
    await state.get_current_soc()
    await state.fetch_prices()
    await state.fetch_weather()
    state.calculate_forecast()
    await state.apply_to_ha(dry_run=True)
    return {"status": "ok", "forecast": state.forecast, "slots": state.inverter_slots}

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("static/index.html", "r") as f: return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=1, access_log=False)
