# EnergyOptimiser Home Assistant Add-on

Smart battery management based on **Nordpool** electricity prices and **Solarman** inverter integration.

## Features
- **1-Click Installation**: Add this repository to your Home Assistant Add-on store.
- **Dynamic Pricing**: Fetches real-time Nordpool prices to optimize charging.
- **Solarman Control**: Automatically toggles grid charging and sets discharge limits on your inverter.
- **Interactive GUI**: Accessible via Home Assistant Ingress.
- **Strategies**:
  - **Maximize Profit**: Arbitrage strategy (Charge low, discharge high).
  - **Maximize Self-Consumption**: Prioritize using solar energy for your home.

## Installation
1. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
2. Click the three dots in the top right and select **Repositories**.
3. Add the following URL: `https://github.com/Ivoozz/energyoptimiser`
4. Find **EnergyOptimiser** in the store and click **Install**.

## Configuration
Go to the **Configuration** tab of the Add-on:
- **Solarman SOC Sensor**: The entity ID for your battery state of charge (e.g., `sensor.solarman_battery_soc`).
- **Charge Switch**: The switch to enable/disable grid charging.
- **Discharge Limit**: The number entity to set the battery discharge threshold.
- **Battery Capacity (kWh)**: Total capacity of your battery bank.
- **Strategy**: Select between "Maximize Profit" or "Maximize Self-Consumption".

## How it works
The EnergyOptimiser calculates the daily average price from Nordpool. 
- In **Maximize Profit** mode, it will force a grid charge when prices are 20% below average and allow discharging when prices are 20% above average.
- In **Maximize Self-Consumption** mode, it prevents grid charging unless the battery is critically low, ensuring maximum use of your solar energy.

## Support
Open an issue on GitHub for support with specific Solarman inverter models.
