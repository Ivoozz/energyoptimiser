from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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

# --- Configuration & Defaults ---
CONFIG_PATH = "/data/config.json"
VERSION = "v2026.3.26"

# Professional Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("energy-optimiser")

DEFAULT_CONFIG = {
    "enabled": False,
    "price_provider": "EnergyZero",
    "market_area": "NL",
    "currency": "EUR",
    "strategy": "Zero on the Meter",
    "charge_threshold_pct": 85.0,
    "discharge_threshold_pct": 115.0,
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
    "solar_arrays": [{"name": "Hoofddak", "kwp": 4.0, "tilt": 35, "azimuth": 180, "efficiency": 0.85}]
}

# --- FastAPI Setup ---
app = FastAPI(docs_url=None, redoc_url=None)

@app.middleware("http")
async def ingress_middleware(request: Request, call_next):
    """
    Handle Home Assistant Ingress sub-paths correctly.
    """
    root_path = request.headers.get("X-Ingress-Path", "")
    if root_path:
        request.scope["root_path"] = root_path.rstrip("/")
    
    # Ensure static files and API calls respect the root_path
    response = await call_next(request)
    return response

# --- Core Optimizer Logic ---
class Optimizer:
    def __init__(self):
        self.config = self.load_config()
        self.prices = []
        self.weather = []
        self.forecast = []
        self.inverter_slots = []
        self.last_update = None
        
        # Robust Timezone loading: Handle empty string or missing env
        tz_env = os.getenv("TZ", "").strip()
        if not tz_env:
            tz_env = "Europe/Amsterdam"
        
        try:
            self.timezone = pytz.timezone(tz_env)
            logger.info(f"Using timezone: {tz_env}")
        except pytz.exceptions.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone '{tz_env}', falling back to Europe/Amsterdam")
            self.timezone = pytz.timezone("Europe/Amsterdam")

        self.current_soc = 50.0
        self._session: Optional[aiohttp.ClientSession] = None

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file with robust fallbacks."""
        config = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    user_config = json.load(f)
                    config.update(user_config)
                    logger.info("Configuration loaded from /data/config.json")
            except Exception as e:
                logger.error(f"Failed to load config: {e}. Using defaults.")
        
        # Rigorous validation of program registers (must be exactly 6)
        for key in ["solarman_prog_times", "solarman_prog_socs", "solarman_prog_grid_charges"]:
            if not isinstance(config.get(key), list) or len(config[key]) != 6:
                logger.warning(f"Invalid length for {key}, resetting to default.")
                config[key] = DEFAULT_CONFIG[key]
        
        return config

    def save_config(self, new_config: Dict[str, Any]):
        """Save configuration to file."""
        # Clean up input and ensure types
        for key in ["charge_threshold_pct", "discharge_threshold_pct", "battery_capacity_kwh", "max_charge_rate_kw"]:
            if key in new_config:
                new_config[key] = float(new_config[key])
        
        if "update_interval_minutes" in new_config:
            new_config["update_interval_minutes"] = int(new_config["update_interval_minutes"])

        self.config = {**DEFAULT_CONFIG, **new_config}
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config, f, indent=2)
            logger.info("Config saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        return self._session

    async def fetch_soc_from_ha(self):
        """Fetch current Battery SOC from Home Assistant API."""
        token = os.getenv("SUPERVISOR_TOKEN")
        entity_id = self.config.get("solarman_battery_soc")
        if not token or not entity_id:
            logger.debug("HA SOC Fetch skipped: Missing token or entity_id")
            return

        url = f"http://supervisor/core/api/states/{entity_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            session = await self.get_session()
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.current_soc = float(data.get("state", 50.0))
                    logger.debug(f"Current SOC: {self.current_soc}%")
                else:
                    logger.warning(f"Failed to fetch SOC from HA: {resp.status}")
        except Exception as e:
            logger.error(f"Error connecting to HA for SOC: {e}")

    async def fetch_prices(self):
        """Fetch electricity prices from EnergyZero (NL)."""
        logger.info("Fetching EnergyZero prices...")
        now_local = datetime.now(self.timezone)
        start_dt = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(days=1, hours=23, minutes=59)
        
        # EnergyZero expects UTC ISO format
        start_utc = start_dt.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_utc = end_dt.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        url = f"https://api.energyzero.nl/v1/energyprices?fromDate={start_utc}&tillDate={end_utc}&interval=4&usageType=1&inclBtw=true"
        
        try:
            session = await self.get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    raw_prices = data.get("Prices", [])
                    if not raw_prices:
                        logger.error("EnergyZero returned empty price list.")
                        return

                    parsed_prices = []
                    for p in raw_prices:
                        try:
                            dt = datetime.fromisoformat(p["readingDate"].replace('Z', '+00:00'))
                            parsed_prices.append({"timestamp": dt, "value": float(p["price"])})
                        except (KeyError, ValueError) as e:
                            logger.error(f"Price parsing error: {e}")
                    
                    if parsed_prices:
                        self.prices = sorted(parsed_prices, key=lambda x: x["timestamp"])
                        logger.info(f"Successfully fetched {len(self.prices)} price points.")
                else:
                    logger.error(f"EnergyZero API error: {resp.status}")
        except Exception as e:
            logger.error(f"EnergyZero connection error: {e}")

    async def fetch_weather(self):
        """Fetch weather data from Meteoserver."""
        key = self.config.get("meteoserver_key")
        loc = self.config.get("meteoserver_location")
        if not key or not loc:
            return

        url = f"https://data.meteoserver.nl/api/uurverwachting.php?key={key}&locatie={loc}"
        try:
            session = await self.get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.weather = data.get("data", [])
                    logger.info(f"Weather data updated for {loc}")
                else:
                    logger.error(f"Meteoserver API error: {resp.status}")
        except Exception as e:
            logger.error(f"Meteoserver connection error: {e}")

    def calculate_solar_yield(self, radiation_wm2: float, hour: int) -> float:
        """Estimate solar yield for all configured arrays."""
        if not self.config.get("solar_enabled") or not self.config.get("solar_arrays"):
            return 0.0
        
        total_kw = 0.0
        for array in self.config.get("solar_arrays", []):
            try:
                kwp = float(array.get("kwp", 0.0))
                tilt = math.radians(float(array.get("tilt", 35.0)))
                azimuth = float(array.get("azimuth", 180.0))
                efficiency = float(array.get("efficiency", 0.85))
                
                # Simple geometric model for solar intensity
                # Azimuth 180 (South) is optimal.
                az_factor = math.cos(math.radians(azimuth - 180.0))
                # Time factor (peak at 12:00)
                time_factor = max(0.0, 1.0 - abs(hour - 12) / 7.0)
                
                yield_kw = (radiation_wm2 / 1000.0) * kwp * efficiency * math.cos(tilt) * time_factor * max(0.1, az_factor)
                total_kw += max(0.0, yield_kw)
            except Exception as e:
                logger.error(f"Solar yield calc error for {array.get('name')}: {e}")
        
        return total_kw

    def calculate_forecast(self):
        """Main strategy logic to determine hourly actions."""
        if not self.prices:
            return

        now = datetime.now(pytz.UTC)
        relevant_prices = [p for p in self.prices if p["timestamp"] >= now - timedelta(hours=1)][:24]
        if not relevant_prices:
            return

        avg_price = sum(p["value"] for p in relevant_prices) / len(relevant_prices)
        strategy = self.config.get("strategy", "Zero on the Meter")
        charge_threshold = float(self.config.get("charge_threshold_pct", 85.0)) / 100.0
        discharge_threshold = float(self.config.get("discharge_threshold_pct", 115.0)) / 100.0
        
        # Build weather lookup
        weather_lookup = {w['tijd'].split(' ')[1][:2]: w for w in self.weather if 'tijd' in w}
        
        new_forecast = []
        for p in relevant_prices:
            lt = p["timestamp"].astimezone(self.timezone)
            hour_str = f"{lt.hour:02d}"
            
            radiation = float(weather_lookup.get(hour_str, {}).get('gr', 0))
            solar_kw = self.calculate_solar_yield(radiation, lt.hour)
            
            price = p["value"]
            action = "IDLE"
            grid_charge = "off"

            # Strategy Implementation
            if strategy == "Zero on the Meter":
                # Goal: Avoid grid costs. Charge when price is negative or very low. 
                # Discharge only when price is high and we have surplus.
                if price < 0:
                    action = "CHARGE (NEG)"
                    grid_charge = "on"
                elif price < (avg_price * 0.5):
                    action = "CHARGE (LOW)"
                    grid_charge = "on"
                elif price > (avg_price * discharge_threshold):
                    action = "DISCHARGE"
                else:
                    action = "AUTONOMOUS"

            elif strategy == "Maximize Profit":
                if price < (avg_price * charge_threshold):
                    action = "CHARGE"
                    grid_charge = "on"
                elif price > (avg_price * discharge_threshold):
                    action = "DISCHARGE"
            
            elif strategy == "Maximize Self-Consumption":
                # Keep battery for evening peak
                if lt.hour >= 17 and lt.hour <= 21:
                    action = "DISCHARGE"
                elif solar_kw > 1.0:
                    action = "SOLAR CHARGE"
                elif price < 0:
                    action = "CHARGE (NEG)"
                    grid_charge = "on"

            new_forecast.append({
                "time": lt.isoformat(),
                "hour": lt.hour,
                "price": round(price, 4),
                "solar_yield": round(solar_kw, 2),
                "action": action,
                "grid_charge": grid_charge,
                "weather": weather_lookup.get(hour_str, {}).get('vvoorsp', 'Clear')
            })

        self.forecast = new_forecast
        self.last_update = datetime.now()
        self.compress_to_slots()

    def compress_to_slots(self):
        """Convert 24h forecast into 6 discrete inverter program slots."""
        if not self.forecast:
            return
        
        raw_slots = []
        current_action = self.forecast[0]["action"]
        current_grid = self.forecast[0]["grid_charge"]
        start_hour = self.forecast[0]["hour"]

        for entry in self.forecast[1:]:
            if entry["action"] != current_action or entry["grid_charge"] != current_grid:
                raw_slots.append({"start": start_hour, "action": current_action, "grid_charge": current_grid})
                current_action = entry["action"]
                current_grid = entry["grid_charge"]
                start_hour = entry["hour"]
        
        raw_slots.append({"start": start_hour, "action": current_action, "grid_charge": current_grid})

        # We must have exactly 6 slots for the inverter
        if len(raw_slots) > 6:
            # Simple compression: take first 5 and merge remaining into 6th
            final_slots = raw_slots[:5]
            final_slots.append(raw_slots[5]) # Simplified
        else:
            final_slots = raw_slots
            # Fill remaining with IDLE slots
            last_h = final_slots[-1]["start"]
            while len(final_slots) < 6:
                last_h = (last_h + 1) % 24
                final_slots.append({"start": last_h, "action": "IDLE", "grid_charge": "off"})

        self.inverter_slots = final_slots[:6]

    async def sync_to_ha(self, dry_run: bool = False):
        """Push the 6 program slots to Home Assistant entities."""
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token:
            logger.debug("Sync to HA skipped: No SUPERVISOR_TOKEN")
            return
        
        if not self.config.get("enabled") and not dry_run:
            logger.info("Sync skipped: Optimizer is disabled.")
            return

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        base_url = "http://supervisor/core/api/services"
        session = await self.get_session()

        logger.info(f"Syncing to HA (Dry Run: {dry_run})")
        
        for i, slot in enumerate(self.inverter_slots):
            try:
                # Time format for Solarman is often HHMM as an integer (e.g. 1400 for 14:00)
                time_val = slot["start"] * 100
                
                # Determine target SOC based on action
                target_soc = 20 # Default floor
                if "CHARGE" in slot["action"]:
                    target_soc = 100
                elif slot["action"] == "AUTONOMOUS":
                    target_soc = 50
                
                grid_service = "switch/turn_on" if slot["grid_charge"] == "on" else "switch/turn_off"
                
                if not dry_run:
                    # Set Time
                    await session.post(f"{base_url}/number/set_value", headers=headers, 
                                     json={"entity_id": self.config["solarman_prog_times"][i], "value": time_val})
                    # Set SOC
                    await session.post(f"{base_url}/number/set_value", headers=headers, 
                                     json={"entity_id": self.config["solarman_prog_socs"][i], "value": target_soc})
                    # Set Grid Charge Switch
                    await session.post(f"{base_url}/{grid_service}", headers=headers, 
                                     json={"entity_id": self.config["solarman_prog_grid_charges"][i]})
                else:
                    logger.info(f"[DRY RUN] Slot {i+1}: Start={time_val}, SOC={target_soc}, Grid={slot['grid_charge']}")
            
            except Exception as e:
                logger.error(f"Error syncing slot {i}: {e}")

    async def run_cycle(self, dry_run: bool = False):
        """Perform one full optimization cycle."""
        await self.fetch_soc_from_ha()
        await self.fetch_prices()
        await self.fetch_weather()
        self.calculate_forecast()
        await self.sync_to_ha(dry_run=dry_run)
        gc.collect()

    async def main_loop(self):
        """Continuous background task."""
        logger.info("Optimizer background loop started.")
        while True:
            try:
                if self.config.get("enabled"):
                    await self.run_cycle()
                
                interval = max(5, self.config.get("update_interval_minutes", 60))
                await asyncio.sleep(interval * 60)
            except Exception as e:
                logger.critical(f"Main loop error: {e}", exc_info=True)
                await asyncio.sleep(60)

# --- State Instance ---
optimizer_state = Optimizer()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(optimizer_state.main_loop())

@app.on_event("shutdown")
async def shutdown_event():
    if optimizer_state._session:
        await optimizer_state._session.close()

# --- API Endpoints ---
@app.get("/api/status")
async def get_status():
    return {
        "version": VERSION,
        "config": optimizer_state.config,
        "forecast": optimizer_state.forecast,
        "inverter_slots": optimizer_state.inverter_slots,
        "last_update": optimizer_state.last_update.isoformat() if optimizer_state.last_update else None,
        "current_soc": optimizer_state.current_soc
    }

@app.post("/api/config")
async def update_config(new_config: dict):
    optimizer_state.save_config(new_config)
    # Trigger immediate update if enabled
    if optimizer_state.config.get("enabled"):
        asyncio.create_task(optimizer_state.run_cycle())
    return {"status": "success"}

@app.post("/api/test_run")
async def run_test_run():
    """Run a test cycle (simulation) without applying changes to HA."""
    await optimizer_state.run_cycle(dry_run=True)
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def index():
    try:
        with open("static/index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("UI not found. Check static directory structure.", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
