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
from datetime import datetime, time, timedelta
import pytz

# Configure Logging
logging.basicConfig(level=logging.INFO)
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
    "solarman_prog_grid_charges": ["switch.solarman_prog1_grid_charge", "switch.solarman_prog2_grid_charge", "switch.solarman_prog3_grid_charge", "switch.solarman_prog4_grid_charge", "switch.solarman_prog5_grid_charge", "switch.solarman_prog6_grid_charge"]
}

# Ingress Middleware to handle sub-paths
@app.middleware("http")
async def set_ingress_root_path(request: Request, call_next):
    ingress_path = request.headers.get("X-Ingress-Path")
    if ingress_path:
        request.scope["root_path"] = ingress_path
    return await call_next(request)

class Optimizer:
    def __init__(self):
        self.config = self.load_config()
        self.prices = []
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
                logger.error(f"Failed to load config: {e}")
        return DEFAULT_CONFIG

    def save_config(self, new_config):
        self.config = new_config
        with open(CONFIG_PATH, "w") as f:
            json.dump(new_config, f, indent=2)

    async def fetch_prices(self):
        try:
            async with aiohttp.ClientSession() as session:
                client = NordPoolClient(session)
                area = self.config.get("nordpool_area", "NL")
                curr = getattr(Currency, self.config.get("currency", "EUR"))
                self.prices = await client.async_get_delivery_period_prices(currency=curr, area=area)
                self.last_update = datetime.now()
                logger.info(f"Nordpool prices updated for {area}")
        except Exception as e:
            logger.error(f"Error fetching Nordpool prices: {e}")

    def calculate_forecast(self):
        if not self.prices: return
        avg_price = sum(p.value for p in self.prices) / len(self.prices)
        charge_t = self.config.get("charge_threshold_pct", 85) / 100.0
        discharge_t = self.config.get("discharge_threshold_pct", 115) / 100.0
        tz = pytz.timezone(self.timezone)
        
        forecast = []
        for p in self.prices[:24]:
            local_time = p.timestamp.astimezone(tz)
            action = "IDLE"
            if self.config.get("strategy") == "Maximize Profit":
                if p.value <= (avg_price * charge_t): action = "CHARGE"
                elif p.value >= (avg_price * discharge_t): action = "DISCHARGE"
            forecast.append({
                "time": local_time.isoformat(),
                "hour": local_time.hour,
                "price": round(p.value, 4),
                "action": action
            })
        self.forecast = forecast
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
        
        while len(raw_slots) > 6: raw_slots.pop()
        while len(raw_slots) < 6:
            new_start = (raw_slots[-1]["start"] + 1) % 24
            raw_slots.append({"start": new_start, "action": raw_slots[-1]["action"]})
        self.inverter_slots = raw_slots

    async def apply_to_ha(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token or not self.inverter_slots or not self.config.get("enabled"): return
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        base_url = "http://supervisor/core/api/services"
        
        for i in range(6):
            slot = self.inverter_slots[i]
            try:
                # Set Time
                requests.post(f"{base_url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_times"][i], "value": slot["start"]*100})
                # Set SOC and Switch
                soc = 100 if slot["action"] == "CHARGE" else 20
                requests.post(f"{base_url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_socs"][i], "value": soc})
                svc = "switch/turn_on" if slot["action"] == "CHARGE" else "switch/turn_off"
                requests.post(f"{base_url}/{svc}", headers=headers, json={"entity_id": self.config["solarman_prog_grid_charges"][i]})
            except Exception as e:
                logger.error(f"HA Sync Error: {e}")

    async def run_loop(self):
        while True:
            if self.config.get("enabled"):
                await self.fetch_prices()
                self.calculate_forecast()
                await self.apply_to_ha()
            await asyncio.sleep(self.config.get("update_interval_minutes", 60) * 60)

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
        "last_update": state.last_update.isoformat() if state.last_update else None
    }

@app.post("/api/config")
async def save_config(new_config: dict):
    state.save_config(new_config)
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("static/index.html", "r") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
