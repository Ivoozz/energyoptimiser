from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pynordpool import NordPoolClient, Currency
import aiohttp
import asyncio
import os
import json
import logging
import requests
import sys
import math
from datetime import datetime, time, timedelta
import pytz
from typing import Optional, List, Dict

# Professional Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("energy-optimiser")

app = FastAPI()

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
    "solarman_prog_times": ["number.solarman_prog1_time", "number.solarman_prog2_time", "number.solarman_prog3_time", "number.solarman_prog4_time", "number.solarman_prog5_time", "number.solarman_prog6_time"],
    "solarman_prog_socs": ["number.solarman_prog1_soc", "number.solarman_prog2_soc", "number.solarman_prog3_soc", "number.solarman_prog4_soc", "number.solarman_prog5_soc", "number.solarman_prog6_soc"],
    "solarman_prog_grid_charges": ["switch.solarman_prog1_grid_charge", "switch.solarman_prog2_grid_charge", "switch.solarman_prog3_grid_charge", "switch.solarman_prog4_grid_charge", "switch.solarman_prog5_grid_charge", "switch.solarman_prog6_grid_charge"],
    "meteoserver_key": "",
    "meteoserver_location": "Utrecht",
    "solar_enabled": False,
    "solar_kwp": 4.0,
    "solar_tilt": 35,
    "solar_azimuth": 180,  # South
    "solar_efficiency": 0.85 # Performance Ratio
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
        self.timezone = os.getenv("TZ", "UTC")

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    return {**DEFAULT_CONFIG, **json.load(f)}
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

    async def fetch_prices(self):
        try:
            async with aiohttp.ClientSession() as session:
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
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.weather = data.get("data", [])
        except Exception as e:
            logger.error(f"Weather Error: {e}")

    def calculate_solar_yield(self, radiation_wm2, hour):
        """
        Estimate solar yield based on radiation, tilt, and azimuth.
        Simplified model for real-time optimization.
        """
        if not self.config.get("solar_enabled"): return 0
        
        kwp = self.config.get("solar_kwp", 4.0)
        tilt = math.radians(self.config.get("solar_tilt", 35))
        azimuth = math.radians(self.config.get("solar_azimuth", 180))
        pr = self.config.get("solar_efficiency", 0.85)
        
        # Simple geometric correction for tilt (heuristic)
        # In a full model, we'd calculate sun position (elevation/azimuth)
        # For now, we assume radiation is global horizontal and apply a fixed correction factor
        # based on hour of day (peak at noon).
        efficiency_factor = math.cos(tilt) # Very rough approximation
        
        # Standard: 1000 W/m2 gives 1kW per 1kWp
        yield_kw = (radiation_wm2 / 1000.0) * kwp * pr * efficiency_factor
        return max(0, yield_kw)

    def calculate_forecast(self):
        if not self.prices: return
        
        avg_p = sum(p.value for p in self.prices) / len(self.prices)
        strategy = self.config.get("strategy", "Maximize Profit")
        charge_t = self.config.get("charge_threshold_pct", 85) / 100.0
        discharge_t = self.config.get("discharge_threshold_pct", 115) / 100.0
        
        tz = pytz.timezone(self.timezone)
        weather_map = {w['tijd'].split(' ')[1][:2]: w for w in self.weather} if self.weather else {}
        
        new_forecast = []
        for p in self.prices[:24]:
            lt = p.timestamp.astimezone(tz)
            h_str = f"{lt.hour:02d}"
            w_point = weather_map.get(h_str, {})
            
            # Global Radiation from Meteoserver (gr)
            rad = float(w_point.get('gr', 0)) if w_point else 0
            solar_yield = self.calculate_solar_yield(rad, lt.hour)
            
            action = "IDLE"
            if strategy == "Maximize Profit":
                # If solar yield is high (> 0.5 kW), we are less likely to charge from grid
                final_charge_t = charge_t
                if solar_yield > 0.5:
                    final_charge_t *= 0.7 # Be more selective
                
                if p.value <= (avg_p * final_charge_t):
                    action = "CHARGE"
                elif p.value >= (avg_p * discharge_t):
                    action = "DISCHARGE"
            
            new_forecast.append({
                "time": lt.isoformat(),
                "hour": lt.hour,
                "price": round(p.value, 4),
                "weather": w_point.get('vvoorsp', 'N/A'),
                "solar_yield": round(solar_yield, 2),
                "action": action
            })
        
        self.forecast = new_forecast
        self.last_update = datetime.now()
        self.map_slots()

    def map_slots(self):
        if not self.forecast: return
        slots = []
        curr_act = self.forecast[0]["action"]
        start_h = self.forecast[0]["hour"]
        for h in self.forecast[1:]:
            if h["action"] != curr_act:
                slots.append({"start": start_h, "action": curr_act})
                curr_act, start_h = h["action"], h["hour"]
        slots.append({"start": start_h, "action": curr_act})
        while len(slots) > 6: slots.pop()
        while len(slots) < 6: slots.append({"start": (slots[-1]["start"]+1)%24, "action": "IDLE"})
        self.inverter_slots = slots

    async def apply_to_ha(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token or not self.inverter_slots or not self.config.get("enabled"): return
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        base_url = "http://supervisor/core/api/services"
        
        for i in range(min(len(self.inverter_slots), 6)):
            slot = self.inverter_slots[i]
            try:
                t_val = slot["start"] * 100
                requests.post(f"{base_url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_times"][i], "value": t_val}, timeout=5)
                soc = 100 if slot["action"] == "CHARGE" else 20
                requests.post(f"{base_url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_socs"][i], "value": soc}, timeout=5)
                svc = "switch/turn_on" if slot["action"] == "CHARGE" else "switch/turn_off"
                requests.post(f"{base_url}/{svc}", headers=headers, json={"entity_id": self.config["solarman_prog_grid_charges"][i]}, timeout=5)
            except: pass

    async def run_loop(self):
        while True:
            try:
                if self.config.get("enabled"):
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

@app.get("/api/status")
async def get_status():
    return {
        "config": state.config,
        "forecast": state.forecast,
        "inverter_slots": state.inverter_slots,
        "last_update": state.last_update.isoformat() if state.last_update else None,
        "timezone": state.timezone
    }

@app.post("/api/config")
async def save_config(new_config: dict):
    state.save_config(new_config)
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("static/index.html", "r") as f: return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
