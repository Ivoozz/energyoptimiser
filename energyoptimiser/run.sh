#!/usr/bin/env bashio

bashio::log.info "EnergyOptimiser v2026.3.36 is initializing..."

# Set System Timezone
export TZ=$(bashio::info.timezone)
bashio::log.info "Timezone set to: ${TZ}"

# Ensure data directory exists
mkdir -p /data

# Start Backend
bashio::log.info "Starting FastAPI Backend..."
cd /app
python3 main.py
