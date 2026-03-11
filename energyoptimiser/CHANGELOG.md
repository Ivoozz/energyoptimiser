# Changelog

## v2026.3.14
- **Price Source Fix**: Completely replaced Zonneplan/Nordpool with a direct **EnergyZero (EPEX Spot NL)** integration. This is the most reliable public source for Dutch dynamic prices and includes VAT.
- **UI Fix**: Resolved the issue where planning fields were not appearing. The **Solarman Registers** are now rendered in a dedicated, bulletproof grid with 6 clear rows (one per program).
- **Persistence**: Enhanced the save logic to ensure all 18 registers and multiple solar arrays are always correctly stored in `/data/config.json`.
- **Descriptions**: Updated all settings with extremely detailed, Dutch-language help-texts and instructions directly in the Admin GUI.

## v2026.3.13
- UI fix for register fields.
- Versioning alignment.
