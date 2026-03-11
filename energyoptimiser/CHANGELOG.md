# Changelog

## v2026.3.22
- **CRITICAL FIX**: Resolved `UnknownTimeZoneError` that caused the application to crash if the `TZ` environment variable was empty or invalid.
- **Sync**: Aligned version numbers across `config.yaml`, `Dockerfile`, `main.py`, and `index.html`.
- **Refinement**: Updated add-on description to reflect the migration to **EnergyZero (EPEX NL)** and **Meteoserver** integration.
- **Reliability**: Enhanced timezone loading with a robust fallback to `Europe/Amsterdam`.

## v2026.3.21
- Complete Ground-up Rewrite.
- Migrated to EnergyZero API.
- Redesigned Admin Hub with 5-tab interface.
- Fixed Solarman register persistence.
