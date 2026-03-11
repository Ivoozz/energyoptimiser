# Changelog

## v2026.3.16
- **Architecture Fix**: Migrated all Home Assistant Supervisor calls to asynchronous **aiohttp**. This eliminates the blocking Python errors and improves performance on Raspberry Pi.
- **Price Engine**: Standardized on **EnergyZero (EPEX NL)** as the primary source. This API is highly stable and publicly accessible without authentication.
- **UI Robustness**: Implemented a **Permanent Register Mapping** UI. The Solarman register fields (Times, SOC, Grid-Charge) now use static IDs and a non-destructive rendering cycle, ensuring they never disappear or empty themselves.
- **Error Handling**: Added defensive parsing for all external APIs (EnergyZero, Meteoserver, HA). The application will now gracefully log errors and continue instead of crashing when keys are missing.
- **Memory Optimization**: Limited the webserver to a single worker and disabled unnecessary metadata generation to keep the RAM footprint minimal.

## v2026.3.15
- Critical UI fix for Solarman registers.
- Fixed persistence mapping.
