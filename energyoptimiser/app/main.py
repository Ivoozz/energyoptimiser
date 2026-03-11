from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pynordpool import NordPoolClient, Currency
import aiohttp
import asyncio
import os
import json
import logging
from datetime import datetime, time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("energy-optimiser")

app = FastAPI()

class OptimizerState:
    def __init__(self):
        self.options = self.load_options()
        self.prices = []
        self.forecast = []
        self.last_update = None
        self.current_action = "IDLE"

    def load_options(self):
        if os.path.exists("/data/options.json"):
            with open("/data/options.json") as f:
                return json.load(f)
        return {
            "enabled": True,
            "nordpool_area": "NL",
            "currency": "EUR",
            "strategy": "Maximize Profit",
            "battery_capacity_kwh": 5.0,
            "charge_threshold_pct": 85,
            "discharge_threshold_pct": 115,
            "update_interval_minutes": 60,
            "solarman_prog_times": [],
            "solarman_prog_socs": [],
            "solarman_prog_grid_charges": []
        }

    async def fetch_prices(self):
        try:
            async with aiohttp.ClientSession() as session:
                client = NordPoolClient(session)
                area = self.options.get("nordpool_area", "NL")
                curr_str = self.options.get("currency", "EUR")
                curr = Currency[curr_str]
                self.prices = await client.async_get_delivery_period_prices(currency=curr, area=area)
                self.last_update = datetime.now()
                logger.info(f"Fetched {len(self.prices)} price points from Nordpool for area {area}")
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")

    def calculate_forecast(self):
        if not self.prices:
            return
        
        avg_price = sum(p.value for p in self.prices) / len(self.prices)
        strategy = self.options.get("strategy", "Maximize Profit")
        charge_threshold = self.options.get("charge_threshold_pct", 85) / 100.0
        discharge_threshold = self.options.get("discharge_threshold_pct", 115) / 100.0
        
        forecast = []
        for p in self.prices[:24]:
            action = "IDLE"
            if strategy == "Maximize Profit":
                if p.value <= (avg_price * charge_threshold):
                    action = "CHARGE"
                elif p.value >= (avg_price * discharge_threshold):
                    action = "DISCHARGE"
            elif strategy == "Maximize Self-Consumption":
                action = "IDLE (Save Solar)"
            
            forecast.append({
                "time": p.timestamp.isoformat(),
                "price": round(p.value, 4),
                "action": action
            })
        
        self.forecast = forecast
        if forecast:
            self.current_action = forecast[0]["action"]

    async def run_optimization_loop(self):
        while True:
            logger.info("Checking automation status...")
            self.options = self.load_options()
            
            if not self.options.get("enabled", True):
                logger.info("EnergyOptimiser is DISABLED. Skipping cycle.")
                self.current_action = "DISABLED"
            else:
                logger.info("Starting optimization cycle...")
                await self.fetch_prices()
                self.calculate_forecast()
                await self.apply_solarman_programs()
            
            interval = self.options.get("update_interval_minutes", 60)
            logger.info(f"Cycle complete. Waiting {interval} minutes.")
            await asyncio.sleep(interval * 60)

    async def apply_solarman_programs(self):
        if not self.options.get("enabled", True):
            return

        token = os.getenv("SUPERVISOR_TOKEN")
        if not token or not self.forecast:
            logger.warning("Missing token or forecast. Skipping HA actions.")
            return
        pass

state = OptimizerState()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(state.run_optimization_loop())

@app.get("/api/status")
async def get_status():
    return {
        "enabled": state.options.get("enabled", True),
        "current_action": state.current_action,
        "last_update": state.last_update.isoformat() if state.last_update else None,
        "strategy": state.options.get("strategy"),
        "forecast": state.forecast,
        "options": state.options
    }

if os.path.exists("/ui/dist"):
    app.mount("/", StaticFiles(directory="/ui/dist", html=True), name="ui")
