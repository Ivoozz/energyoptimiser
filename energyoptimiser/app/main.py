from fastapi import FastAPI, Request
from pynordpool import NordPoolClient, Currency
import aiohttp
import asyncio
import os
import json

app = FastAPI()

# Strategy logic
# 1. Maximize Profit: Charge when price < threshold, discharge when price > high threshold
# 2. Maximize Self-Consumption: Prioritize battery for home usage, only charge from grid if critically low

class Optimizer:
    def __init__(self):
        self.battery_capacity = 5.0
        self.soc = 0
        self.strategy = "Maximize Profit"
        self.prices = []

    async def fetch_prices(self):
        async with aiohttp.ClientSession() as session:
            client = NordPoolClient(session)
            # Use 'NL' for Netherlands or a config param
            self.prices = await client.async_get_delivery_period_prices(currency=Currency.EUR, area="NL")
        return self.prices

    def calculate_action(self):
        if not self.prices:
            return "No data"
        
        # Simple Logic for Profit
        avg_price = sum(p.value for p in self.prices) / len(self.prices)
        current_price = self.prices[0].value # Simplified
        
        if self.strategy == "Maximize Profit":
            if current_price < (avg_price * 0.8):
                return "CHARGE"
            elif current_price > (avg_price * 1.2):
                return "DISCHARGE"
        
        elif self.strategy == "Maximize Self-Consumption":
            # Don't charge from grid unless battery < 10%
            if self.soc < 10:
                return "CHARGE"
            else:
                return "IDLE (Use Solar)"
        
        return "IDLE"

optimizer = Optimizer()

@app.get("/api/config")
async def get_config():
    # Load from HA Addon options
    if os.path.exists("/data/options.json"):
        with open("/data/options.json") as f:
            return json.load(f)
    return {"error": "Options not found"}

@app.get("/api/status")
async def get_status():
    prices = await optimizer.fetch_prices()
    action = optimizer.calculate_action()
    return {
        "strategy": optimizer.strategy,
        "current_action": action,
        "prices": prices[:24]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
