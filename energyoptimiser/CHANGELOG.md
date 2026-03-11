# Changelog

## v2026.3.26
- **Bugfix**: Resolved the issue where the "Simulatie Run" did not update the dashboard. Fixed a naming mismatch between the frontend and backend endpoints (`/api/test_run` vs `/api/simulate`).
- **Optimization**: Ensured the simulation cycle correctly populates the in-memory forecast before refreshing the UI.

## v2026.3.25
- **UI/UX**: Designed and implemented a brand new, modern, and sleek icon and logo for the application.
- **Maintenance**: Synchronized versioning and metadata across all files.

## v2026.3.24
- **Bugfix**: Fixed the "UI not found" error by correcting the static file path in the backend to use relative container paths instead of absolute development paths.
- **Maintenance**: Synchronized versioning across all components.

## v2026.3.23
- **Mandate**: Internalized the strict versioning and description synchronization protocol.
- **Maintenance**: Confirmed all metadata is consistent across config.yaml, Dockerfile, main.py, and index.html.

## v2026.3.22
- **CRITICAL FIX**: Resolved `UnknownTimeZoneError` that caused the application to crash if the `TZ` environment variable was empty or invalid.
- **Sync**: Aligned version numbers across all files.
- **Reliability**: Enhanced timezone loading with a robust fallback to `Europe/Amsterdam`.

## v2026.3.21
- Complete Ground-up Rewrite.
- Migrated to EnergyZero API.
- Redesigned Admin Hub with 5-tab interface.
- Fixed Solarman register persistence.
