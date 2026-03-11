# Changelog

## v2026.3.5
- **Optimization**: Fully optimized for **Raspberry Pi** Home Assistant installations.
- **Optimization**: Migrated to a **Multi-Stage Docker build** to reduce image size and startup time.
- **Optimization**: Reduced memory footprint by limiting Uvicorn to a single worker and disabling unnecessary docs.
- **Optimization**: Integrated persistent **aiohttp session reuse** to minimize CPU overhead and network latency.
- **Reliability**: Added manual garbage collection hints to prevent memory creep on low-RAM devices.
- **Reliability**: Disabled verbose access logging to protect SD cards from excessive I/O writes.

## v2026.3.4
- Feature: Integrated Solar Panel yield actively into the decision-making algorithm.
- Feature: Automatic Grid-Charge Suppression based on solar forecasts.
- Feature: Real-time SOC Monitoring from Home Assistant.

## v2026.3.3
- Extensive descriptions and help-texts added directly into the Web UI.
- Polished settings dashboard.
