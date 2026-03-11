from fastapi import FastAPI, HTTPException
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

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("energy-optimiser")

app = FastAPI()

class OptimizerState:
    def __init__(self):
        self.options = self.load_options()
        self.prices = []
        self.forecast = []
        self.inverter_slots = []
        self.last_update = None
        self.current_action = "IDLE"
        self.timezone = "UTC"

    def load_options(self):
        if os.path.exists("/data/options.json"):
            with open("/data/options.json") as f:
                return json.load(f)
        return {
            "enabled": True,
            "nordpool_area": "NL",
            "currency": "EUR",
            "strategy": "Maximize Profit",
            "charge_threshold_pct": 85,
            "discharge_threshold_pct": 115,
            "update_interval_minutes": 60,
            "solarman_prog_times": [],
            "solarman_prog_socs": [],
            "solarman_prog_grid_charges": []
        }

    def get_ha_info(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token:
            return
        headers = {"Authorization": f"Bearer {token}"}
        try:
            r = requests.get("http://supervisor/info", headers=headers)
            if r.status_code == 200:
                data = r.json()
                self.timezone = data.get("data", {}).get("timezone", "UTC")
                logger.info(f"Detected Home Assistant Timezone: {self.timezone}")
        except Exception as e:
            logger.error(f"Error getting HA info: {e}")

    async def fetch_prices(self):
        try:
            async with aiohttp.ClientSession() as session:
                client = NordPoolClient(session)
                area = self.options.get("nordpool_area", "NL")
                curr_str = self.options.get("currency", "EUR")
                curr = Currency[curr_str]
                # Prices are in UTC usually from Nordpool
                self.prices = await client.async_get_delivery_period_prices(currency=curr, area=area)
                self.last_update = datetime.now()
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")

    def calculate_forecast(self):
        if not self.prices:
            return
        
        avg_price = sum(p.value for p in self.prices) / len(self.prices)
        strategy = self.options.get("strategy", "Maximize Profit")
        charge_threshold = self.options.get("charge_threshold_pct", 85) / 100.0
        discharge_threshold = self.options.get("discharge_threshold_pct", 115) / 100.0
        
        # Localize prices to HA Timezone
        tz = pytz.timezone(self.timezone)
        
        forecast = []
        for p in self.prices[:24]:
            local_time = p.timestamp.astimezone(tz)
            action = "IDLE"
            if strategy == "Maximize Profit":
                if p.value <= (avg_price * charge_threshold):
                    action = "CHARGE"
                elif p.value >= (avg_price * discharge_threshold):
                    action = "DISCHARGE"
            
            forecast.append({
                "time": local_time.isoformat(),
                "hour": local_time.hour,
                "price": round(p.value, 4),
                "action": action
            })
        
        self.forecast = forecast
        self.map_to_inverter_slots()

    def map_to_inverter_slots(self):
        """
        Condense 24h forecast into 6 discrete time slots for Solarman/Deye.
        """
        if not self.forecast:
            return

        # 1. Group by same action
        raw_slots = []
        current_action = self.forecast[0]["action"]
        start_hour = self.forecast[0]["hour"]
        
        for h in self.forecast[1:]:
            if h["action"] != current_action:
                raw_slots.append({"start": start_hour, "action": current_action})
                current_action = h["action"]
                start_hour = h["hour"]
        raw_slots.append({"start": start_hour, "action": current_action})

        # 2. Merge if > 6
        while len(raw_slots) > 6:
            # Simple merge: find the shortest duration or least impactful change
            # For now, just merge the last two until we hit 6
            raw_slots[-2]["action"] = raw_slots[-1]["action"] # or some other merging logic
            raw_slots.pop()

        # 3. Padding if < 6
        while len(raw_slots) < 6:
            # Just add dummy slots at the end with same action as last
            last_start = raw_slots[-1]["start"]
            new_start = (last_start + 1) % 24
            raw_slots.append({"start": new_start, "action": raw_slots[-1]["action"]})

        self.inverter_slots = raw_slots
        logger.info(f"Mapped forecast to 6 inverter slots: {self.inverter_slots}")

    async def apply_to_ha(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token or not self.inverter_slots:
            return

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        base_url = "http://supervisor/core/api/services"

        prog_times = self.options.get("solarman_prog_times", [])
        prog_socs = self.options.get("solarman_prog_socs", [])
        prog_grid_charges = self.options.get("solarman_prog_grid_charges", [])

        for i in range(min(len(self.inverter_slots), 6)):
            slot = self.inverter_slots[i]
            
            # 1. Set Time (format HHMM as integer usually, e.g. 2300)
            if i < len(prog_times):
                time_val = slot["start"] * 100 # e.g. 14 -> 1400
                requests.post(f"{base_url}/number/set_value", headers=headers, json={
                    "entity_id": prog_times[i], "value": time_val
                })

            # 2. Set SOC and Grid Charge
            soc_val = 20 # Default discharge/idle
            grid_charge = "off"
            
            if slot["action"] == "CHARGE":
                soc_val = 100
                grid_charge = "on"
            elif slot["action"] == "DISCHARGE":
                soc_val = 20 # Allow discharge
            
            if i < len(prog_socs):
                requests.post(f"{base_url}/number/set_value", headers=headers, json={
                    "entity_id": prog_socs[i], "value": soc_val
                })
            
            if i < len(prog_grid_charges):
                service = "switch/turn_on" if grid_charge == "on" else "switch/turn_off"
                requests.post(f"{base_url}/{service}", headers=headers, json={
                    "entity_id": prog_grid_charges[i]
                })

    async def run_optimization_loop(self):
        self.get_ha_info()
        while True:
            self.options = self.load_options()
            if self.options.get("enabled", True):
                await self.fetch_prices()
                self.calculate_forecast()
                await self.apply_to_ha()
            
            interval = self.options.get("update_interval_minutes", 60)
            await asyncio.sleep(interval * 60)

state = OptimizerState()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(state.run_optimization_loop())

@app.get("/api/status")
async def get_status():
    return {
        "enabled": state.options.get("enabled", True),
        "timezone": state.timezone,
        "forecast": state.forecast,
        "inverter_slots": state.inverter_slots,
        "last_update": state.last_update.isoformat() if state.last_update else None,
        "options": state.options
    }

if os.path.exists("/ui/dist"):
    app.mount("/", StaticFiles(directory="/ui/dist", html=True), name="ui")
