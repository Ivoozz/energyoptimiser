#!/usr/bin/with-contenv bashio

# Get Supervisor Token
export SUPERVISOR_TOKEN=$SUPERVISOR_TOKEN

echo "Starting EnergyOptimiser Add-on..."

# Start the Python Backend (FastAPI)
# It will also serve the static UI files from /ui/dist
cd /app
python3 main.py
