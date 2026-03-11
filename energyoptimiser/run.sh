#!/usr/bin/with-contenv bashio

bashio::log.info "Starting EnergyOptimiser Add-on (v1.5.1)..."

# Set Timezone
TZ=$(bashio::info.timezone)
export TZ=$TZ
bashio::log.info "System Timezone set to: ${TZ}"

# Navigate to app directory
cd /app

# Ensure we use the virtual environment python
bashio::log.info "Launching Python backend..."
exec /opt/venv/bin/python3 main.py
