# ReSource_KZW

## Ziel

Dieses Projekt soll die Grundwasserstände der Messstelle 1 in Reinickendorf (Berlin) regelmäßig erfassen und im ThingsBoard als Telemetrie anzeigen. Die Daten sollen täglich aktualisiert werden, ohne dass ein lokaler PC dauerhaft laufen muss.

## Datenquelle

Die Grundwasserstände der Messstelle 1 sind im Wasserportal Berlin veröffentlicht:

- Messstelle 1 – Grundwasserstand: https://wasserportal.berlin.de/station.php?anzeige=g&thema=gws&station=1

Der offizielle Leitfaden **Wasserportal Berlin – Getting Started with the API (2024)** beschreibt den Abruf als HTTP-GET mit CSV-Ausgabe. Für Grundwasserstände sind diese Parameter relevant:

| Parameter | Wert/Bedeutung |
| --- | --- |
| `anzeige=d` | Daten herunterladen |
| `station=1` | Messstelle 1 |
| `thema=gws` | Grundwasserstand |
| `sreihe=ew` | Einzelwerte |
| `smode=c` | CSV-Ausgabe |
| `exportthema=gw` | Grundwasser |
| `sdatum`, `senddatum` | Beginn und Ende des gewünschten Zeitraums (`TT.MM.JJJJ`) |

Die Messreihen-Konfiguration liegt in [`measurement-series.json`](measurement-series.json). Das Python-Skript baut daraus pro Reihe einen GET-Aufruf gemäß Leitfaden. Das PDF wird hier nicht kopiert; der offizielle Leitfaden ist unter [Wasserportal Berlin – Getting Started with the API (PDF)](https://wasserportal01.stadt-berlin.de/download/wasserportal_berlin_getting_data.pdf) erreichbar (abgerufen am 21.11.2026).

## Architektur

Das Projekt soll in der Regel so funktionieren:

1. Beim ersten Lauf ruft die GitHub Action jede konfigurierte Messreihe ab ihrem Startdatum ab.
2. Der Workflow aktualisiert zuerst `groundwater-data.json` und veröffentlicht damit die HTML-Datensicherung unabhängig von ThingsBoard.
3. Danach sendet er noch nicht übertragene Messpunkte mit ihren Messzeitstempeln in begrenzten Paketen an ThingsBoard.
4. Abruf- und Upload-Fortschritt werden getrennt in `groundwater-sync-state.json` gespeichert. Scheitert ThingsBoard, bleiben die HTML-Daten verfügbar und der nicht bestätigte Upload wird später erneut versucht.
5. In ThingsBoard wird ein Dashboard mit Zeitreihe für die Messstelle erstellt.

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

## Synchronisierung

Die GitHub Action benötigt `THINGSBOARD_URL` als Repository-Variable und `MESSSTELLE_1` als Repository-Secret. Sie benötigt außerdem Schreibrechte für den Repository-Inhalt, um den Synchronisierungsstand und die Messreihe zu aktualisieren. Änderungen an `groundwater-sync-state.json` und `groundwater-data.json` lösen keinen weiteren Push-Workflow aus. Der Job ist auf 15 Minuten begrenzt; ein abgelehnter ThingsBoard-Paket-Upload wird nicht in Tausende Einzelaufrufe aufgeteilt.

Neue Reihen werden als weitere Einträge in `measurement-series.json` konfiguriert. `token_env` benennt die passende Umgebungsvariable; für neue ThingsBoard-Geräte muss die entsprechende GitHub-Secret-Variable zusätzlich im Workflow hinterlegt werden. Stoff-ID und Parametername müssen anhand des Leitfadens und der Daten der konkreten Messstelle verifiziert werden.

Die HTML lädt `groundwater-data.json` automatisch. Sie bietet eine Auswahl der konfigurierten Messreihe und zwei Schieberegler für Anfang und Ende des angezeigten Zeitraums; Diagramm, neuester Wert und Tabelle richten sich nach dem ausgewählten Zeitraum. Bei direktem Öffnen der lokalen HTML-Datei ruft sie die Datendatei aus dem `main`-Branch dieses öffentlichen GitHub-Repositories ab; auf einer Website wird die Datendatei vom selben Speicherort geladen. ThingsBoard-Zugangsdaten werden dabei nicht im Browser verwendet.

Mit dem Button **Mann-Kendall-Modus** kann derselbe ausgewählte Zeitraum statistisch auf einen Trend geprüft werden. Die Ansicht zeigt Trendrichtung, Kendall-τ, p-Wert und Signifikanzniveau. Standardmäßig werden Jahresmittel verwendet, damit das Analyse-Diagramm vom Detaildiagramm der Einzelmessungen unterscheidbar bleibt. Optional können Einzelmessungen, Monatsmittel oder Jahresmittel ausgewertet und der Theil-Sen-Schätzer als Trendsteigung in `m/Jahr` eingeblendet werden. Zusätzlich werden die ausgewählten Daten in einem Analyse-Diagramm mit optionaler Theil-Sen-Trendlinie sowie Kendall-τ auf einer Skala von `-1` bis `+1` dargestellt. Der Mann-Kendall-Modus ist keine saisonale Mann-Kendall-Auswertung; saisonale Schwankungen werden erst in einer späteren Ausbaustufe korrigiert.

Wenn ThingsBoard einen Lauf ablehnt, bleibt der Abruf-Fortschritt erhalten, während der Upload-Fortschritt nur bis zum letzten bestätigten Paket reicht. Ein erneuter Lauf versucht den noch offenen Upload erneut; bereits bestätigte Pakete werden übersprungen.

## Nächste Schritte

- [ ] Datenformat und Abrufmethode der Messstelle prüfen
- [ ] Grundwasserwert, Einheit und Zeitstempel verifizieren
- [ ] ThingsBoard-Gerät und Device Access Token einrichten
- [ ] GitHub Actions Workflow für täglichen Datenabruf und Upload erstellen
- [ ] Dashboard in ThingsBoard mit Zeitreihe erstellen
- [ ] Regelmäßige Ausführung prüfen und überwachen

## Hinweis

Dieses Projekt ist aktuell wie ein technischer Entwurf angelegt und wird schrittweise umgesetzt. Das Ziel ist eine automatisierte, tägliche Darstellung des Grundwasserstands in ThingsBoard ohne lokale Ausführung auf einem PC.
