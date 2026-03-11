# Changelog

## v2026.3.1
- **Feature**: Integrated **Meteoserver.nl** for high-resolution Dutch weather forecasts.
- **Feature**: Added **Solar Reduction Factor** to adjust grid charging based on sunny weather predictions.
- **Enhancement**: Improved 6-slot mapping algorithm for Solarman inverters.
- **Enhancement**: Complete UI overhaul with detailed forecast tables and mapped slot views.
- **Fix**: Re-structured Docker build for **Home Assistant 2026.3.1** compatibility (Alpine 3.23 + Python 3.14).
- **Fix**: Fixed Ingress sub-path issues with dynamic root middleware.
- **Stability**: Added extremely verbose logging for easier troubleshooting.

## v2026.3.0
- Ground-up rebuild.
- Migrated to S6-Overlay v3.
- Integrated internal web dashboard.
