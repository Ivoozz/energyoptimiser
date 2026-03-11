# Changelog

## v2026.3.8
- **Feature**: Added **Zero on the Meter (0 op de Meter)** strategy. This strategy focuses on absolute minimum grid interaction, only charging from the grid during negative prices or when critically necessary to offset future expensive imports.
- **Feature**: Dashboard now explicitly shows **Grid Charge Status** (ON/OFF) for every calculated hour and every inverter program slot.
- **Feature**: Real-time **Autonomy visualization**. The dashboard now summarizes the current strategy and its impact on grid import.
- **Reliability**: Optimized configuration persistence logic to ensure all advanced settings (multiple arrays, program maps) are correctly migrated and preserved during updates.
- **UX**: Polished dashboard with a dedicated "Status Card" for the active strategy.

## v2026.3.7
- Persistence guaranteed via /data directory.
- Multiple solar array support.
- Dry run testing mode.
