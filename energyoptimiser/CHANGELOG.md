# Changelog

## v2026.3.17
- **Major Fix**: Completely replaced Zonneplan/Nordpool with **EnergyZero (EPEX Spot NL)** public API for high-reliability Dutch electricity prices.
- **UI Fix**: Re-implemented the **Solarman Registers** configuration with a bulletproof static rendering method. 18 registers (6x Time, 6x SOC, 6x Grid-Charge) are now permanently visible and editable.
- **Persistence**: Enhanced the loading and saving logic to explicitly prevent empty arrays or data loss during updates or restarts.
- **Detailed Descriptions**: Rewrote all Dutch help-texts and instructions for every single variable in the Admin GUI.
- **Performance**: Standardized on asynchronous `aiohttp` for all Home Assistant and external API calls.

## v2026.3.16
- Architecture improvements for Raspberry Pi.
- Standardized on EnergyZero pricing source.
