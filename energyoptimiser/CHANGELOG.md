# Changelog

## v2026.3.36
- **Feature**: Added **API Status Indicators** for EnergyZero, Meteoserver and HomeAssistant.
- **Feature**: Added **Dynamic Solar Arrays** configuration for multiple sets of panels.
- **Feature**: Re-implemented all Inverter Program Registers (P1-P6).
- **Feature**: Added **System Health Indicator** (Glowing LED status) on dashboard.
- **Feature**: Re-implemented strategy selection and battery thresholds.
- **Maintenance**: Synchronized all versioning to v2026.3.36 for clean Home Assistant update.

## v2026.3.35
- **Build Fix**: Resolved "unknown error" during image building by adding `--break-system-packages` to pip.
- **Reliability**: Fixed `run.sh` to correctly invoke the python binary.
