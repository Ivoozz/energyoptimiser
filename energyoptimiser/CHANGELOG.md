# Changelog

## v2026.3.18
- **Major Reliability Fix**: Implemented a **Persistent Register Mapping** system in the Admin GUI. The 18 program register fields (Times, SOC, Grid-Charge) now use static, unique HTML IDs and a non-destructive rendering cycle. This guarantees they will never be empty or disappear during updates.
- **Price Engine**: Finalized migration to **EnergyZero (EPEX Spot NL)** as the primary, high-reliability price source.
- **Async HA Integration**: Migrated all remaining Supervisor and Core API calls to asynchronous `aiohttp` to prevent blocking the Python event loop.
- **Detailed Descriptions**: Fully populated all help-texts and instructions in the GUI for every single variable.

## v2026.3.17
- Replaced NordPool with EnergyZero API.
- Structural UI fixes.
