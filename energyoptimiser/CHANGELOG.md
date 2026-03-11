# Changelog

## v2026.3.30
- **Validation**: Removed all dummy/placeholder data from the simulation and optimization logic. The system now requires and uses only real-time data from external APIs.
- **Transparency**: Added an "API Status" indicator bar to the dashboard. You can now see at a glance if EnergyZero (Prices), Meteoserver (Weather), and Home Assistant (SOC) are responding correctly (Green = Success, Red = Fail).
- **Diagnostics**: Implemented detailed error reporting in the backend to identify exactly why an API fetch might fail.
- **Maintenance**: Synchronized versioning across all components.

## v2026.3.29
- Reliability: Implemented a "Dummy Data Fallback" for simulations (Reverted in v2026.3.30).
- Robustness: Improved EnergyZero price fetching date ranges.

## v2026.3.28
- Feature: Added Minimum and Maximum Battery SOC limits.
