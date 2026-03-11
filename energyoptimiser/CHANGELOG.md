# Changelog

## v2026.3.4
- **Feature**: Integrated **Zonnepanelen (Solar Panels)** yield actively into the decision-making algorithm.
- **Feature**: Automatic **Grid-Charge Suppression**: The system now skips charging from the grid during cheap hours if the predicted solar yield is sufficient to fill the battery capacity.
- **Feature**: Real-time **SOC Monitoring**: The optimizer now fetches the live Battery State of Charge (SOC) from Home Assistant before every calculation cycle.
- **Enhancement**: Improved solar yield estimation model with time-of-day efficiency curves.
- **Enhancement**: Refined "Maximize Profit" strategy to balance price-arbitrage with upcoming solar production.

## v2026.3.3
- Extensive descriptions and help-texts added directly into the Web UI.
- Polished settings dashboard.

## v2026.3.2
- Initial Solar Panel Integration logic.
- Meteoserver.nl weather integration.
