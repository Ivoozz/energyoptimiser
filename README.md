# EnergyOptimiser: De Ultieme Gids voor Slimme Accu-Optimalisatie

Welkom bij **EnergyOptimiser**. Dit programma is ontworpen om je thuisaccu intelligent aan te sturen op basis van de dynamische uurtarieven van **Nordpool**, specifiek geoptimaliseerd voor inverters die gebruik maken van de **Solarman** integratie in Home Assistant.

---

## 1. Installatie (De "1-Click" Methode)

1.  Open **Home Assistant**.
2.  Navigeer naar **Instellingen** > **Add-ons**.
3.  Klik rechtsonder op **Add-on Store**.
4.  Klik rechtsboven op de drie puntjes (Menu) en kies **Opslagplaatsen**.
5.  Plak de volgende URL in het veld: `https://github.com/Ivoozz/energyoptimiser` en klik op **Toevoegen**.
6.  Vernieuw de pagina. Je ziet nu **EnergyOptimiser** onderaan de lijst staan.
7.  Klik op de add-on en klik op **Installeren**.

---

## 2. Configuratie (Stap-voor-Stap)

Zodra de installatie is voltooid, moet je de add-on koppelen aan je Solarman sensoren. Ga naar het tabblad **Configuratie** binnen de add-on.

### Essentiële Instellingen:
- **Nordpool Area:** Stel je regio in (bijv. `NL` voor Nederland, `BE` voor België).
- **Solarman Battery SOC:** De entiteit-ID van je batterijpercentage (bijv. `sensor.solarman_battery_soc`).
- **Charge Switch:** De switch-entiteit die het laden vanaf het net (Grid Charge) aan- of uitzet (bijv. `switch.solarman_grid_charge`).
- **Discharge Limit:** De entiteit waarmee je de ontlaadlimiet instelt (bijv. `number.solarman_battery_discharge_limit`).
- **Battery Capacity (kWh):** De totale bruikbare capaciteit van je accu (bijv. `10.5`).
- **Strategy:** Kies tussen:
    - `Maximize Profit`: Laadt de accu op als de stroom spotgoedkoop is en ontlaadt als de stroom duur is (Arbitrage).
    - `Maximize Self-Consumption`: Gebruikt de accu primair om je eigen zonne-energie op te slaan en te verbruiken, en laadt alleen bij van het net als de accu bijna leeg is.

Klik op **Opslaan** en start de add-on.

---

## 3. Gebruik van de GUI (Bedieningspaneel)

EnergyOptimiser heeft een ingebouwd bedieningspaneel dat via **Ingress** werkt.

1.  Klik in de Home Assistant zijbalk op **EnergyOptimiser** (of ga naar de add-on pagina en klik op "Open Web UI").
2.  **Dashboard:** Hier zie je direct de huidige actie van het programma (`IDLE`, `CHARGE`, of `DISCHARGE`).
3.  **Prijsgrafiek & Forecast:** De GUI toont een grafiek van de komende 24 uur. 
    - De **blauwe lijn** zijn de Nordpool prijzen per uur.
    - De **gekleurde blokken** onderaan de grafiek geven aan wat het programma gaat doen:
        - **Groen:** Gepland opladen vanaf het net.
        - **Rood:** Gepland ontladen (om duur verbruik te dekken).
        - **Grijs:** Stand-by (gebruik van zonne-energie of batterij).

---

### 6-Programma Regeling (Solarman/Deye/Sunsynk)
Veel moderne omvormers (zoals Deye en Sunsynk) die gebruik maken van Solarman loggers, werken met een systeem van **6 tijdsperiodes** (ook wel Time-of-Use genoemd).

EnergyOptimiser analyseert de 24-uurs prijsverwachting en verdeelt deze over de 6 beschikbare slots:
1.  **Tijden:** De add-on stelt de starttijden van de 6 programma's in om de goedkoopste en duurste uren te dekken.
2.  **Grid Charge:** Per slot wordt bepaald of de accu vanaf het net geladen moet worden (`Grid Charge` AAN) of juist moet ontladen voor je huis (`Grid Charge` UIT + lage SOC target).
3.  **SOC Targets:** De doelen voor de batterijlading (bijv. 100% tijdens goedkope uren, 20% tijdens dure uren) worden automatisch naar de omvormer gepusht.

**Let op:** Zorg ervoor dat je in Home Assistant de entiteiten voor `Prog1 Time`, `Prog1 SOC`, `Prog1 Grid Charge`, etc. hebt geconfigureerd via je Solarman integratie. Vul deze entiteit-IDs in bij de configuratie van deze add-on.

1.  **Data ophalen:** Het haalt de meest recente prijzen op bij Nordpool.
2.  **Analyse:** Het berekent de gemiddelde prijs van de dag. 
3.  **Besluitvorming:**
    - Is de huidige prijs **lager dan 85%** van het daggemiddelde? Dan wordt de `Charge Switch` aangezet.
    - Is de huidige prijs **hoger dan 115%** van het daggemiddelde? Dan wordt de ontlaadlimiet verlaagd zodat de accu kan leveren.
4.  **Automatisering:** De commando's worden direct naar je Solarman inverter gestuurd via de interne Home Assistant verbinding.

---

## 5. Veelgestelde Vragen (FAQ)

**V: Werkt dit met elke Solarman inverter?**
A: Ja, zolang je de `homeassistant-solarman` integratie hebt geïnstalleerd en de juiste registers (zoals Grid Charge) zichtbaar zijn als entiteiten in Home Assistant.

**V: Kan ik handmatig ingrijpen?**
A: Zodra je de add-on stopt, stopt ook de automatische aansturing. Je kunt dan weer handmatig je inverter bedienen.

**V: Wat als Nordpool geen data geeft?**
A: Het programma blijft in de laatste veilige stand (`IDLE`) totdat de verbinding is hersteld.

---

## Ondersteuning & Bijdragen
Heb je problemen met het instellen van je specifieke omvormer? Open een issue op onze GitHub pagina!
