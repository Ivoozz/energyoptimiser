from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pynordpool import NordPoolClient, Currency
import aiohttp
import asyncio
import os
import json
import logging
from datetime import datetime, timedelta

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
            "nordpool_area": "NL",
            "currency": "EUR",
            "strategy": "Maximize Profit",
            "battery_capacity_kwh": 5.0,
            "update_interval_minutes": 60
        }

    async def fetch_prices(self):
        try:
            async with aiohttp.ClientSession() as session:
                client = NordPoolClient(session)
                area = self.options.get("nordpool_area", "NL")
                curr = getattr(Currency, self.options.get("currency", "EUR"))
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
        
        forecast = []
        for p in self.prices[:24]:
            action = "IDLE"
            if strategy == "Maximize Profit":
                if p.value < (avg_price * 0.85):
                    action = "CHARGE"
                elif p.value > (avg_price * 1.15):
                    action = "DISCHARGE"
            elif strategy == "Maximize Self-Consumption":
                # In a real scenario, this would check solar forecast vs load
                # For this simplified logic, we prioritize battery state
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
            logger.info("Starting optimization cycle...")
            self.options = self.load_options()
            await self.fetch_prices()
            self.calculate_forecast()
            
            # Here we would call Home Assistant API to set switches/numbers
            # Using SUPERVISOR_TOKEN and HA URL
            await self.apply_ha_actions()
            
            interval = self.options.get("update_interval_minutes", 60)
            logger.info(f"Optimization complete. Sleeping for {interval} minutes.")
            await asyncio.sleep(interval * 60)

    async def apply_ha_actions(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token:
            logger.warning("No SUPERVISOR_TOKEN found. Skipping HA actions.")
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        url = "http://supervisor/core/api/services"
        
        # Logic to toggle switches based on self.current_action
        # Example: switch.turn_on/off for solarman_charge_switch
        # This part requires the actual entity IDs from self.options
        pass

state = OptimizerState()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(state.run_optimization_loop())

@app.get("/api/status")
async def get_status():
    return {
        "current_action": state.current_action,
        "last_update": state.last_update.isoformat() if state.last_update else None,
        "strategy": state.options.get("strategy"),
        "forecast": state.forecast,
        "options": state.options
    }

# Serve static files for the UI
if os.path.exists("/ui/dist"):
    app.mount("/", StaticFiles(directory="/ui/dist", html=True), name="ui")
