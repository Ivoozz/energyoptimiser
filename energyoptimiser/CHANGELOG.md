# Changelog

## v2026.3.6
- **Feature**: Support for **Multiple Solar Arrays**. You can now add multiple sets of panels (e.g., front and back of the house) with individual tilt and azimuth settings.
- **Feature**: Integrated **Test Optimalisatie (Dry Run)** button. Test your configuration and see the planned actions on the dashboard without sending any commands to your inverter.
- **Feature**: Full control over **Program SOC and Grid-Charge registers**. All 18 Solarman registers (6x Time, 6x SOC, 6x Grid Charge) are now configurable in the UI.
- **Algorithm**: The decision-making engine now explicitly uses the summed yield of all solar arrays to intelligently suppress grid-charging if the sun can fill the battery.
- **Safety**: Strictly uses **percentages (SOC)** for all battery calculations; voltage-based logic is explicitly avoided for better compatibility and safety.
- **UI**: Completely redesigned settings page with dynamic array management and extensive help-texts.

## v2026.3.5
- Optimization for Raspberry Pi.
- Multi-Stage Docker build.
- Reduced memory footprint and SD card protection.
