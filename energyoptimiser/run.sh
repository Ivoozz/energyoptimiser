#!/usr/bin/env bashio

bashio::log.info "Starting EnergyOptimiser Add-on (v1.5.2)..."

# In S6 v3, environment variables are already populated.
# We can still use bashio to get specific info.

# Set Timezone
TZ=$(bashio::info.timezone)
export TZ=$TZ
bashio::log.info "System Timezone set to: ${TZ}"

# Navigate to app directory
cd /app

# Ensure we use the virtual environment python
bashio::log.info "Launching Python backend..."
exec /opt/venv/bin/python3 main.py
