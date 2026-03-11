# Changelog

## v2026.3.7
- **Feature**: **Persistence Guaranteed**. Investigated and verified that all configuration is stored in the `/data` partition, which is preserved by the Home Assistant Supervisor across add-on updates. 
- **Feature**: **Grid-Charge Slot Transparency**. Added per-program Grid Charge status to the dashboard and forecast tables.
- **Feature**: **Dry Run testing**. Test your configuration without sending actual Modbus commands to your inverter.
- **Enhancement**: Expanded UI settings to include all 18 Solarman registers (Time, SOC, Grid-Charge) for 6 programs.
- **Enhancement**: Support for multiple solar arrays with individual parameters.
- **Reliability**: Strictly SOC-based logic; voltage-based control is excluded for stability.

## v2026.3.6
- Multiple Solar Array support.
- Manual dry-run test mode.
- Advanced configuration UI.
