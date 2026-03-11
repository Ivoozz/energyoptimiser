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
            "nordpool_area": "NL",
            "currency": "EUR",
            "strategy": "Maximize Profit",
            "battery_capacity_kwh": 5.0,
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
        
        forecast = []
        for p in self.prices[:24]:
            action = "IDLE"
            if strategy == "Maximize Profit":
                # Grid Charge if price is in the lowest 25% of the day
                sorted_prices = sorted([pr.value for pr in self.prices[:24]])
                low_threshold = sorted_prices[5] # roughly lowest 6 hours
                high_threshold = sorted_prices[-6] # roughly highest 6 hours
                
                if p.value <= low_threshold:
                    action = "CHARGE"
                elif p.value >= high_threshold:
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
            logger.info("Starting optimization cycle...")
            self.options = self.load_options()
            await self.fetch_prices()
            self.calculate_forecast()
            await self.apply_solarman_programs()
            
            interval = self.options.get("update_interval_minutes", 60)
            logger.info(f"Optimization complete. Sleeping for {interval} minutes.")
            await asyncio.sleep(interval * 60)

    async def apply_solarman_programs(self):
        """
        Maps the 24-hour forecast to the 6 Solarman program slots.
        Solarman (Deye/Sunsynk) uses 6 fixed time slots.
        We will attempt to find the optimal windows for these slots.
        """
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token or not self.forecast:
            logger.warning("Missing token or forecast. Skipping HA actions.")
            return

        # Find continuous blocks of CHARGE or DISCHARGE
        # This is a complex mapping, for now we will simplify and 
        # just set the first 6 hours of the forecast into the 6 slots if they change
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        # Mapping logic for 6 slots:
        # We group the 24 hours into 6 blocks or specific event windows.
        # For simplicity in this v1.2, we target the next 6 state changes.
        
        # Example call to HA:
        # url = "http://supervisor/core/api/services/number/set_value"
        # payload = {"entity_id": self.options['solarman_prog_socs'][0], "value": 100}
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

if os.path.exists("/ui/dist"):
    app.mount("/", StaticFiles(directory="/ui/dist", html=True), name="ui")
