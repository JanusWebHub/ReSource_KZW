# ReSource_KZW

## Ziel

Dieses Projekt soll die Grundwasserstände der Messstelle 1 in Reinickendorf (Berlin) regelmäßig erfassen und im ThingsBoard als Telemetrie anzeigen. Die Daten sollen täglich aktualisiert werden, ohne dass ein lokaler PC dauerhaft laufen muss.

## Datenquelle

Die bisher verfügbaren Grundwasserstände sind im Wasserportal Berlin veröffentlicht:

- Messstelle 1 – Grundwasserstand: https://wasserportal.berlin.de/station.php?anzeige=g&thema=gws&station=1

Die genaue Struktur der Daten muss beim Abruf geprüft werden. Mögliche Formate sind z. B. HTML-Tabelle, CSV-Download oder eine separate API oder Exportdatei. Die Nutzung der Quelle und die Lizenz-/Nutzungsbedingungen sollten dabei berücksichtigt werden.

## Architektur

Das Projekt soll in der Regel so funktionieren:

1. GitHub Action ruft jeden Tag die Messstelle ab.
2. Der Workflow verarbeitet die Daten und extrahiert den aktuellen Grundwasserwert.
3. Der Wert wird als Telemetrie an ThingsBoard gesendet.
4. In ThingsBoard wird ein Dashboard mit Zeitreihe für die Messstelle erstellt.

GitHub dient hier als Code- und Workflow-Hosting. Es führt die tägliche Aktualisierung in der Cloud aus; der lokale Rechner ist dafür nicht erforderlich.

## Geplante Komponenten

- GitHub Repository zur Verwaltung des Codes
- GitHub Actions Workflow für den täglichen Lauf
- ThingsBoard-Gerät für Messstelle 1 (Reinickendorf)
- ThingsBoard-Dashboard zur Darstellung des Grundwasserstands
- Optional: Skript oder Parser für CSV/HTML/API-Auswertung

## Geplante Messwertfelder

| Feld | Beschreibung |
| --- | --- |
| `timestamp` | Zeitstempel der Messung |
| `groundwater_level` | Messwert des Grundwasserstands |
| `station_id` | Kennung der Messstelle, hier 1 |
| `station_name` | Name bzw. Lage der Messstelle, Reinickendorf |
| `unit` | Einheit des Messwerts, falls in den Daten angegeben |

Die genaue Bezeichnung und Einheit der Messwerte muss nach Prüfung der Datenquelle festgelegt werden.

## ThingsBoard-Setup (Plan)

In ThingsBoard soll für die Messstelle ein eigenes Gerät angelegt werden. Danach wird ein Access Token oder ein passender Zugangsschlüssel verwendet, damit der GitHub-Workflow Werte als Telemetrie senden kann.

Typischer Ablauf:

1. Gerät in ThingsBoard anlegen
2. Device Access Token erzeugen
3. Token als GitHub Actions Secret speichern
4. Workflow sendet Messwerte als Telemetrie an das Gerät
5. Dashboard für Zeitreihe und Trendansicht erstellen

## Sicherheit

Zugangsdaten, insbesondere ThingsBoard-Token oder andere sensible Informationen, dürfen nicht im öffentlichen Repository gespeichert werden. Diese Informationen sollen als GitHub Actions Secrets oder lokale Umgebungsvariablen hinterlegt werden.

## Nächste Schritte

- [ ] Datenformat und Abrufmethode der Messstelle prüfen
- [ ] Grundwasserwert, Einheit und Zeitstempel verifizieren
- [ ] ThingsBoard-Gerät und Device Access Token einrichten
- [ ] GitHub Actions Workflow für täglichen Datenabruf und Upload erstellen
- [ ] Dashboard in ThingsBoard mit Zeitreihe erstellen
- [ ] Regelmäßige Ausführung prüfen und überwachen

## Hinweis

Dieses Projekt ist aktuell wie ein technischer Entwurf angelegt und wird schrittweise umgesetzt. Das Ziel ist eine automatisierte, tägliche Darstellung des Grundwasserstands in ThingsBoard ohne lokale Ausführung auf einem PC.
