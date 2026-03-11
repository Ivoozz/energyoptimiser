# EnergyOptimiser v2026.3.1

Slim energiebeheer voor je thuisaccu, volledig geïntegreerd met Home Assistant, Nordpool prijzen en Meteoserver weersvoorspellingen.

## 🚀 Nieuw in v2026.3.1
- **Meteoserver Integratie**: Gebruik hoge-resolutie KNMI data om je laadstrategie aan te passen op de zonverwachting.
- **Solar Reduction**: Bespaar nog meer door minder van het net te laden als de zon morgen gaat schijnen.
- **Verbeterde UI**: Bekijk je planning tot in detail in de vernieuwde web-interface.
- **HA 2026.3.1 Support**: Volledig compatibel met de nieuwste Python 3.14 omgeving van Home Assistant.

## 🛠 Installatie
1. Voeg deze repository toe aan de Home Assistant Add-on Store: `https://github.com/Ivoozz/energyoptimiser`
2. Installeer de **EnergyOptimiser** add-on.
3. Start de add-on en open de **Web UI** via de zijbalk.

## ⚙️ Configuratie via Web UI
In plaats van de standaard HA instellingen, gebruik je de knop **"Instellingen"** in de EnergyOptimiser Web UI voor een rijkere ervaring:

### 1. Nordpool & Meteoserver
- **API Key**: Vraag een gratis of betaalde sleutel aan op [Meteoserver.nl](https://meteoserver.nl/).
- **Locatie**: Vul je stad in voor lokale voorspellingen.
- **Solar Reductie Factor**: Stel in hoe agressief je wilt besparen op netstroom bij zon. (0.5 betekent 50% minder grid-charging bij zon).

### 2. Solarman Registers
Zorg dat je de entiteit-IDs van je Solarman (Deye/Sunsynk) omvormer bij de hand hebt:
- **SOC Sensor**: `sensor.solarman_battery_soc`
- **Tijd Registers**: De 6 registers die de starttijden regelen (number).
- **SOC Registers**: De 6 registers die de doel-percentages regelen (number).
- **Grid Charge Switches**: De 6 schakelaars om laden vanaf het net te forceren (switch).

## 📊 Hoe het werkt
De EnergyOptimiser draait een continue loop (standaard elk uur):
1. Haalt de actuele **Nordpool** prijzen op.
2. Haalt de **Meteoserver** verwachting op.
3. Berekent de optimale strategie (Maximize Profit of Self-Consumption).
4. Mapt de 24-uurs planning naar de **6 fysieke slots** van je omvormer.
5. Pusht de tijden, SOC-doelen en Grid-Charge status direct naar Home Assistant.

---
**Publisher:** FixjeICT  
**Support:** info@fixjeict.nl
