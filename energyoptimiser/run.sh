#!/usr/bin/with-contenv bashio

bashio::log.info "Starting EnergyOptimiser Add-on..."

# Map options from config.yaml to environment variables if needed
# or let main.py read /data/options.json directly.

# Set the timezone if available
TZ=$(bashio::info.timezone)
export TZ=$TZ
bashio::log.info "Using timezone: ${TZ}"

# Start the Python Backend
cd /app
exec python3 main.py
