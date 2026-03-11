from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pynordpool import NordPoolClient, Currency
import aiohttp
import asyncio
import os
import json
import logging
import requests
from datetime import datetime, time, timedelta
import pytz
from typing import Optional

# Setup logging
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

class OptimizerState:
    def __init__(self):
        self.config = self.load_config()
        self.prices = []
        self.forecast = []
        self.inverter_slots = []
        self.last_update = None
        self.timezone = "UTC"

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    return {**DEFAULT_CONFIG, **json.load(f)}
            except:
                return DEFAULT_CONFIG
        return DEFAULT_CONFIG

    def save_config(self, new_config):
        self.config = new_config
        with open(CONFIG_PATH, "w") as f:
            json.dump(new_config, f, indent=2)

    async def get_ha_timezone(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token: return
        headers = {"Authorization": f"Bearer {token}"}
        try:
            r = requests.get("http://supervisor/info", headers=headers)
            if r.status_code == 200:
                self.timezone = r.json().get("data", {}).get("timezone", "UTC")
        except: pass

    async def fetch_prices(self):
        try:
            async with aiohttp.ClientSession() as session:
                client = NordPoolClient(session)
                area = self.config.get("nordpool_area", "NL")
                curr = getattr(Currency, self.config.get("currency", "EUR"))
                self.prices = await client.async_get_delivery_period_prices(currency=curr, area=area)
                self.last_update = datetime.now()
        except Exception as e:
            logger.error(f"Price fetch error: {e}")

    def calculate_forecast(self):
        if not self.prices: return
        avg = sum(p.value for p in self.prices) / len(self.prices)
        charge_t = self.config.get("charge_threshold_pct", 85) / 100.0
        discharge_t = self.config.get("discharge_threshold_pct", 115) / 100.0
        tz = pytz.timezone(self.timezone)
        
        forecast = []
        for p in self.prices[:24]:
            lt = p.timestamp.astimezone(tz)
            action = "IDLE"
            if self.config.get("strategy") == "Maximize Profit":
                if p.value <= (avg * charge_t): action = "CHARGE"
                elif p.value >= (avg * discharge_t): action = "DISCHARGE"
            forecast.append({"time": lt.isoformat(), "hour": lt.hour, "price": round(p.value, 4), "action": action})
        self.forecast = forecast
        self.map_slots()

    def map_to_6_slots(self):
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
        while len(slots) < 6: slots.append({"start": (slots[-1]["start"]+1)%24, "action": slots[-1]["action"]})
        self.inverter_slots = slots

    def map_slots(self): self.map_to_6_slots()

    async def apply_to_ha(self):
        token = os.getenv("SUPERVISOR_TOKEN")
        if not token or not self.inverter_slots or not self.config.get("enabled"): return
        headers = {"Authorization": f"Bearer {token}"}
        url = "http://supervisor/core/api/services"
        for i, slot in enumerate(self.inverter_slots[:6]):
            try:
                # Time
                requests.post(f"{url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_times"][i], "value": slot["start"]*100})
                # SOC & Grid
                soc = 100 if slot["action"]=="CHARGE" else 20
                requests.post(f"{url}/number/set_value", headers=headers, json={"entity_id": self.config["solarman_prog_socs"][i], "value": soc})
                svc = "switch/turn_on" if slot["action"]=="CHARGE" else "switch/turn_off"
                requests.post(f"{url}/{svc}", headers=headers, json={"entity_id": self.config["solarman_prog_grid_charges"][i]})
            except: pass

    async def loop(self):
        await self.get_ha_timezone()
        while True:
            if self.config.get("enabled"):
                await self.fetch_prices()
                self.calculate_forecast()
                await self.apply_to_ha()
            await asyncio.sleep(self.config.get("update_interval_minutes", 60) * 60)

state = OptimizerState()

@app.on_event("startup")
async def startup(): asyncio.create_task(state.loop())

@app.get("/api/status")
async def get_status():
    return {
        "config": state.config,
        "forecast": state.forecast,
        "inverter_slots": state.inverter_slots,
        "last_update": state.last_update.isoformat() if state.last_update else None
    }

@app.post("/api/config")
async def save_config(config: dict):
    state.save_config(config)
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EnergyOptimiser Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-slate-900 text-white font-sans min-h-screen">
    <nav class="bg-slate-800 p-4 border-b border-slate-700">
        <div class="container mx-auto flex justify-between items-center">
            <h1 class="text-xl font-bold flex items-center gap-2">
                <span class="text-green-400">⚡</span> EnergyOptimiser
            </h1>
            <div class="flex gap-4">
                <button onclick="showPage('dashboard')" class="hover:text-green-400 transition">Dashboard</button>
                <button onclick="showPage('config')" class="hover:text-green-400 transition">Instellingen</button>
            </div>
        </div>
    </nav>

    <main class="container mx-auto p-6">
        <!-- Dashboard -->
        <div id="page-dashboard" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="bg-slate-800 p-6 rounded-xl border border-slate-700">
                    <p class="text-slate-400 text-sm">Status</p>
                    <h2 id="status-enabled" class="text-2xl font-bold text-red-400">Gedeactiveerd</h2>
                </div>
                <div class="bg-slate-800 p-6 rounded-xl border border-slate-700">
                    <p class="text-slate-400 text-sm">Huidige Actie</p>
                    <h2 id="status-action" class="text-2xl font-bold text-blue-400">IDLE</h2>
                </div>
                <div class="bg-slate-800 p-6 rounded-xl border border-slate-700">
                    <p class="text-slate-400 text-sm">Laatste Update</p>
                    <h2 id="status-update" class="text-2xl font-bold">--:--</h2>
                </div>
            </div>

            <div class="bg-slate-800 p-6 rounded-xl border border-slate-700">
                <h3 class="text-lg font-semibold mb-4">Nordpool Prijsverwachting (24u)</h3>
                <canvas id="priceChart" class="w-full h-64"></canvas>
            </div>
        </div>

        <!-- Config -->
        <div id="page-config" class="hidden space-y-6 max-w-4xl mx-auto">
            <div class="bg-slate-800 p-8 rounded-xl border border-slate-700">
                <h3 class="text-xl font-bold mb-6">Systeem Configuratie</h3>
                <form id="configForm" class="space-y-4">
                    <div class="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg">
                        <div>
                            <label class="font-bold">Automatisering Activeren</label>
                            <p class="text-sm text-slate-400">Zet het algoritme aan of uit.</p>
                        </div>
                        <input type="checkbox" name="enabled" class="w-6 h-6 rounded accent-green-500">
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium mb-1">Nordpool Regio</label>
                            <input type="text" name="nordpool_area" class="w-full bg-slate-900 border border-slate-600 p-2 rounded">
                        </div>
                        <div>
                            <label class="block text-sm font-medium mb-1">Valuta</label>
                            <input type="text" name="currency" class="w-full bg-slate-900 border border-slate-600 p-2 rounded">
                        </div>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium mb-1">Laaddrempel (%)</label>
                            <input type="number" name="charge_threshold_pct" class="w-full bg-slate-900 border border-slate-600 p-2 rounded">
                        </div>
                        <div>
                            <label class="block text-sm font-medium mb-1">Ontlaaddrempel (%)</label>
                            <input type="number" name="discharge_threshold_pct" class="w-full bg-slate-900 border border-slate-600 p-2 rounded">
                        </div>
                    </div>

                    <hr class="border-slate-700">
                    <h4 class="font-bold">Solarman Entiteiten (Sensor / Numbers)</h4>
                    <div class="space-y-2">
                        <label class="block text-sm">Batterij SOC Sensor</label>
                        <input type="text" name="solarman_battery_soc" class="w-full bg-slate-900 border border-slate-600 p-2 rounded">
                    </div>

                    <button type="submit" class="w-full bg-green-600 hover:bg-green-500 py-3 rounded-lg font-bold transition">Instellingen Opslaan</button>
                </form>
            </div>
        </div>
    </main>

    <script>
        let chart = null;

        function showPage(id) {
            document.getElementById('page-dashboard').classList.add('hidden');
            document.getElementById('page-config').classList.add('hidden');
            document.getElementById('page-' + id).classList.remove('hidden');
        }

        async function loadData() {
            const r = await fetch('/api/status');
            const data = await r.json();
            
            document.getElementById('status-enabled').innerText = data.config.enabled ? 'ACTIEF' : 'GEDEACTIVEERD';
            document.getElementById('status-enabled').className = 'text-2xl font-bold ' + (data.config.enabled ? 'text-green-400' : 'text-red-400');
            document.getElementById('status-update').innerText = data.last_update ? new Date(data.last_update).toLocaleTimeString() : '--:--';
            
            // Populate Form
            const form = document.getElementById('configForm');
            for (let k in data.config) {
                if (form[k]) {
                    if (form[k].type === 'checkbox') form[k].checked = data.config[k];
                    else form[k].value = data.config[k];
                }
            }

            // Update Chart
            updateChart(data.forecast);
        }

        function updateChart(forecast) {
            const ctx = document.getElementById('priceChart').getContext('2d');
            const labels = forecast.map(f => new Date(f.time).getHours() + ':00');
            const prices = forecast.map(f => f.price);
            const colors = forecast.map(f => f.action === 'CHARGE' ? 'rgba(74, 222, 128, 0.5)' : (f.action === 'DISCHARGE' ? 'rgba(248, 113, 113, 0.5)' : 'rgba(148, 163, 184, 0.2)'));

            if (chart) chart.destroy();
            chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Nordpool Prijs (€)',
                        data: prices,
                        backgroundColor: colors,
                        borderColor: '#fff',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { beginAtZero: true } }
                }
            });
        }

        document.getElementById('configForm').onsubmit = async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const config = {};
            formData.forEach((v, k) => {
                if (k === 'enabled') config[k] = true;
                else if (['charge_threshold_pct', 'discharge_threshold_pct', 'battery_capacity_kwh', 'max_charge_rate_kw', 'update_interval_minutes'].includes(k)) config[k] = parseFloat(v);
                else config[k] = v;
            });
            if (!config.enabled) config.enabled = false;
            
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            alert('Instellingen opgeslagen!');
            loadData();
        };

        setInterval(loadData, 30000);
        loadData();
    </script>
</body>
</html>
    """
