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
from datetime import datetime, time, timedelta
import pytz
from typing import Optional, List, Dict

# Extremely Verbose Logging for Debugging
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()
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
    "solar_reduction_factor": 0.5  # How much to reduce grid charging if sun is expected (0 to 1)
}

# Middleware for Ingress
@app.middleware("http")
async def ingress_middleware(request: Request, call_next):
    ingress_path = request.headers.get("X-Ingress-Path")
    if ingress_path:
        request.scope["root_path"] = ingress_path.rstrip("/")
        logger.debug(f"Ingress Active: Root path set to {request.scope['root_path']}")
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
        logger.info(f"Optimizer Engine Initialized. TZ: {self.timezone}")

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    data = json.load(f)
                    logger.info("Config successfully loaded from persistent storage.")
                    return {**DEFAULT_CONFIG, **data}
            except Exception as e:
                logger.error(f"Config load failed: {e}")
        return DEFAULT_CONFIG

    def save_config(self, new_config):
        self.config = new_config
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(new_config, f, indent=2)
            logger.info("New configuration saved and applied.")
        except Exception as e:
            logger.error(f"Config save failed: {e}")

    async def fetch_prices(self):
        logger.info("Fetching Nordpool prices...")
        try:
            async with aiohttp.ClientSession() as session:
                client = NordPoolClient(session)
                area = self.config.get("nordpool_area", "NL")
                curr = getattr(Currency, self.config.get("currency", "EUR"), Currency.EUR)
                self.prices = await client.async_get_delivery_period_prices(currency=curr, area=area)
                logger.debug(f"Fetched {len(self.prices)} price points.")
        except Exception as e:
            logger.error(f"Nordpool Fetch Failed: {e}", exc_info=True)

    async def fetch_weather(self):
        key = self.config.get("meteoserver_key")
        loc = self.config.get("meteoserver_location")
        if not key:
            logger.info("Meteoserver key missing. Skipping weather fetch.")
            return
        
        logger.info(f"Fetching weather for {loc} from Meteoserver...")
        url = f"https://data.meteoserver.nl/api/uurverwachting.php?key={key}&locatie={loc}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.weather = data.get("data", [])
                        logger.debug(f"Fetched {len(self.weather)} weather points.")
                    else:
                        logger.error(f"Meteoserver API Error: {response.status}")
        except Exception as e:
            logger.error(f"Weather Fetch Failed: {e}")

    def calculate_forecast(self):
        if not self.prices: return
        
        avg_price = sum(p.value for p in self.prices) / len(self.prices)
        strategy = self.config.get("strategy", "Maximize Profit")
        charge_t = self.config.get("charge_threshold_pct", 85) / 100.0
        discharge_t = self.config.get("discharge_threshold_pct", 115) / 100.0
        solar_factor = self.config.get("solar_reduction_factor", 0.5)
        
        tz = pytz.timezone(self.timezone)
        new_forecast = []
        
        # Match weather to prices
        weather_map = {w['tijd'].split(' ')[1][:2]: w for w in self.weather} if self.weather else {}

        for p in self.prices[:24]:
            local_time = p.timestamp.astimezone(tz)
            hour_str = f"{local_time.hour:02d}"
            w_point = weather_map.get(hour_str, {})
            
            # Simple solar potential logic: high temp and low cloud/precip = sun
            # Meteoserver doesn't give direct 'cloud' easily in free uursverwachting sometimes, 
            # but we can look at 'vvoorsp' or precipitation.
            is_sunny = False
            if w_point:
                # Basic heuristic: if it's day time and not raining/cloudy
                if 8 <= local_time.hour <= 18 and float(w_point.get('precip', 0)) < 0.1:
                    is_sunny = True

            action = "IDLE"
            if strategy == "Maximize Profit":
                final_charge_t = charge_t
                if is_sunny:
                    # If sun is expected, be MORE selective with grid charging
                    final_charge_t *= (1 - solar_factor)
                    logger.debug(f"Solar detected at {hour_str}:00. Reduced charge threshold to {final_charge_t}")

                if p.value <= (avg_price * final_charge_t):
                    action = "CHARGE"
                elif p.value >= (avg_price * discharge_t):
                    action = "DISCHARGE"
            
            new_forecast.append({
                "time": local_time.isoformat(),
                "hour": local_time.hour,
                "price": round(p.value, 4),
                "weather": w_point.get('vvoorsp', 'N/A'),
                "is_sunny": is_sunny,
                "action": action
            })
        
        self.forecast = new_forecast
        self.last_update = datetime.now()
        self.map_to_6_slots()

    def map_to_6_slots(self):
        if not self.forecast: return
        raw_slots = []
        curr_act = self.forecast[0]["action"]
        start_h = self.forecast[0]["hour"]
        
        for h in self.forecast[1:]:
            if h["action"] != curr_act:
                raw_slots.append({"start": start_h, "action": curr_act})
                curr_act, start_h = h["action"], h["hour"]
        raw_slots.append({"start": start_h, "action": curr_act})
        
        # Squeeze logic
        while len(raw_slots) > 6:
            # Find the slot with the shortest duration and merge it with neighbors
            # For simplicity, we just pop for now, but a more advanced merge would be better.
            raw_slots.pop()
            
        while len(raw_slots) < 6:
            new_start = (raw_slots[-1]["start"] + 1) % 24
            raw_slots.append({"start": new_start, "action": "IDLE"})
            
        self.inverter_slots = raw_slots
        logger.info(f"Mapped Strategy to 6 Slots: {self.inverter_slots}")

    async def apply_to_ha(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token or not self.inverter_slots or not self.config.get("enabled"): return
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        base_url = "http://supervisor/core/api/services"
        
        logger.info("Pushing schedule to Home Assistant / Solarman registers...")
        for i in range(min(len(self.inverter_slots), 6)):
            slot = self.inverter_slots[i]
            try:
                # Set Time (HHMM)
                t_val = slot["start"] * 100
                requests.post(f"{base_url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_times"][i], "value": t_val}, timeout=10)
                
                # Set SOC & Grid Charge
                soc = 100 if slot["action"] == "CHARGE" else 20
                requests.post(f"{base_url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_socs"][i], "value": soc}, timeout=10)
                
                svc = "switch/turn_on" if slot["action"] == "CHARGE" else "switch/turn_off"
                requests.post(f"{base_url}/{svc}", headers=headers, json={"entity_id": self.config["solarman_prog_grid_charges"][i]}, timeout=10)
                
                logger.debug(f"Slot {i+1} synced: {slot['start']}:00 -> {slot['action']}")
            except Exception as e:
                logger.error(f"Sync failed for slot {i+1}: {e}")

    async def run_loop(self):
        logger.info("Optimizer Loop Started.")
        while True:
            try:
                if self.config.get("enabled"):
                    await self.fetch_prices()
                    await self.fetch_weather()
                    self.calculate_forecast()
                    await self.apply_to_ha()
                else:
                    logger.info("Optimizer is STANDBY (Disabled in config).")
                
                wait_min = self.config.get("update_interval_minutes", 60)
                logger.debug(f"Loop finished. Sleeping for {wait_min} minutes.")
                await asyncio.sleep(wait_min * 60)
            except Exception as e:
                logger.critical(f"LOOP CRASH: {e}", exc_info=True)
                await asyncio.sleep(60)

state = Optimizer()

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(state.run_loop())

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
    try:
        with open("static/index.html", "r") as f:
            return f.read()
    except Exception as e:
        return HTMLResponse(content=f"Error loading UI: {e}", status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
