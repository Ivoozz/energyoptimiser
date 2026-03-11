# Changelog

## v2026.3.29
- **Reliability**: Implemented a "Dummy Data Fallback" for simulations. If the API fails to fetch prices during a test run, the system now injects a synthetic price curve so you can still verify the UI and logic.
- **Robustness**: Improved the EnergyZero price fetching logic with a wider date range and more resilient date parsing to handle different API response formats.
- **Maintenance**: Synchronized versioning across all components.

## v2026.3.28
- Feature: Added Minimum and Maximum Battery SOC limits.
- Logic: The optimization engine now respects these limits when calculating program targets.
- UI: Added dedicated input fields for SOC limits in the System tab.

## v2026.3.27
- UI/UX: Re-designed the application icon and logo with a "Cyber-Tech" aesthetic.

## v2026.3.26
- Bugfix: Resolved the issue where the "Simulatie Run" did not update the dashboard.
