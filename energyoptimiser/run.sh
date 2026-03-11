#!/usr/bin/with-contenv bashio

echo "Starting EnergyOptimiser Add-on..."

# Start the Python Backend (FastAPI)
cd /app
python3 main.py
