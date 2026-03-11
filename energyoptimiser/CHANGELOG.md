# Changelog

## v2026.3.15
- **CRITICAL UI FIX**: Redesigned the **Solarman Registers** configuration to use a permanent, static rendering method. Fields can no longer "disappear" or be empty upon loading.
- **Persistence Fix**: Enhanced the save logic to explicitly map stable HTML IDs to the configuration file, ensuring 100% data integrity for all 18 registers.
- **Pricing**: Default price provider set to **EnergyZero (EPEX Spot NL)** for reliable, public data without authentication.
- **Solar**: Improved multi-array management with clearer labels and help-texts.

## v2026.3.14
- Replaced Zonneplan with EnergyZero API.
- Rebuilt register UI grid.
