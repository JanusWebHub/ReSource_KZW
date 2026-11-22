# ReSource_KZW

Dieses Projekt sammelt Grundwasserstände der Messstelle 1 in Reinickendorf
(Berlin), speichert sie in diesem Repository und überträgt neue Messpunkte
optional an ThingsBoard.

## Aktueller Stand

- Die Messreihe wird aus dem Wasserportal Berlin abgerufen.
- Die Daten werden in [`groundwater-data.json`](groundwater-data.json)
  als HTML-Datensicherung gespeichert.
- Die HTML-Anzeige in [`index.html`](index.html) kann mehrere Messreihen,
  Zeitbereiche und eine Mann-Kendall-Trendanalyse darstellen.
- Eine GitHub Action aktualisiert die Daten täglich.
- Die Übertragung an ThingsBoard erfolgt paketweise und speichert den letzten
  bestätigten Upload getrennt vom Abruf-Fortschritt.
- Für die konfigurierte Messstelle sind Stand 21.11.2026:
  - 12.641 Messpunkte gespeichert
  - frühester gespeicherter Messpunkt:
    01.11.1953
  - neuester gespeicherter Messpunkt:
    09.11.2026

Der Abruf ist unabhängig vom ThingsBoard-Upload: Wenn die Übertragung
fehlschlägt, bleiben die Daten und der Abruf-Fortschritt erhalten. Bereits
bestätigte Pakete werden beim nächsten Lauf nicht erneut gesendet.

## Datenquelle

Die Messwerte stammen aus dem Wasserportal Berlin:

https://wasserportal.berlin.de/station.php?anzeige=g&thema=gws&station=1

Der Abruf erfolgt als HTTP-GET mit CSV-Ausgabe. Die relevanten Parameter sind
in [`measurement-series.json`](measurement-series.json) hinterlegt:

| Parameter | Wert |
| --- | --- |
| `anzeige` | `d` – Daten herunterladen |
| `station` | `1` – Messstelle Reinickendorf |
| `thema` | `gws` – Grundwasserstand |
| `sreihe` | `ew` – Einzelwerte |
| `smode` | `c` – CSV-Ausgabe |
| `exportthema` | `gw` – Grundwasser |
| `nstoffid` | Stoff-ID der Messreihe |
| `nstoffid2` | zusätzliche Stoff-ID |
| `sdatum`, `senddatum` | Beginn und Ende in `TT.MM.JJJJ` |

Der offizielle Leitfaden ist lokal als
[`wasserportal_berlin_getting_data.pdf`](wasserportal_berlin_getting_data.pdf)
vorhanden.

## Messreihen

Die Konfiguration wird in [`measurement-series.json`](measurement-series.json)
geführt. Aktuell enthält sie die Messreihe
`station-1-groundwater-level`:

| Feld | Wert |
| --- | --- |
| Station | 1, Reinickendorf |
| Parameter | Grundwasserstand |
| Telemetrie-Schlüssel | `groundwater_level` |
| Einheit | `m ü. NHN` |
| Startdatum | 01.11.1953 |
| Spalte in der CSV | 1 |
| Plausibilitätsbereich | -100 bis 1000 |

Weitere Messstellen oder Parameter können als eigener Eintrag mit einer
eigenen ThingsBoard-Secret-Umgebung ergänzt werden.

## Dateien

| Datei | Zweck |
| --- | --- |
| [`scripts/sync_groundwater.py`](scripts/sync_groundwater.py) | Abruf, CSV-Auswertung, Datensicherung und ThingsBoard-Upload |
| [`measurement-series.json`](measurement-series.json) | Konfiguration der Messreihen |
| [`groundwater-data.json`](groundwater-data.json) | Gespeicherte Messwerte für die HTML-Anzeige |
| [`groundwater-sync-state.json`](groundwater-sync-state.json) | Abruf- und Upload-Fortschritt je Messreihe |
| [`index.html`](index.html) | Browseransicht mit Diagramm, Tabelle und Trendanalyse |
| [`tests/test_sync_groundwater.py`](tests/test_sync_groundwater.py) | Unit-Tests für CSV, HTTP-Aufruf und Upload-Payload |
| [`.github/workflows/update-groundwater.yml`](.github/workflows/update-groundwater.yml) | Täglicher GitHub-Action-Workflow |

## HTML-Anzeige

Die HTML-Datei ist unter GitHub Pages oder durch direktes Öffnen nutzbar.
Dabei lädt sie [`groundwater-data.json`](groundwater-data.json) aus dem
veröffentlichten Repository bzw. vom gleichen Speicherort.

Die Ansicht bietet:

- Auswahl einer konfigurierten Messreihe
- neuesten Messwert und Messdatum im gewählten Zeitraum
- frei einstellbaren Start- und Endzeitpunkt
- Zeitreihendiagramm
- Tabelle mit Messdatum und Messwert
- Mann-Kendall-Modus für Einzelmessungen, Monatsmittel oder Jahresmittel
- optionalen Theil-Sen-Schätzer in `m/Jahr`
- Kendall-τ auf einer Skala von -1 bis +1

Der Mann-Kendall-Modus ist keine saisonale Mann-Kendall-Auswertung. Saisonale
Effekte werden in einer späteren Ausbaustufe berücksichtigt.

## Automatische Synchronisierung

Der Workflow [`.github/workflows/update-groundwater.yml`](.github/workflows/update-groundwater.yml)
läuft täglich um 06:00 UTC sowie bei jedem Push auf `main` und lässt sich
manuell starten.

### Ablauf

1. Unit-Tests werden ausgeführt.
2. Neue Daten werden ab dem gespeicherten Abrufdatum abgerufen.
3. `groundwater-data.json` und der Abruf-Fortschritt werden veröffentlicht.
4. Noch nicht bestätigte Messpunkte werden in Paketen mit höchstens 20
   Messpunkten an ThingsBoard gesendet.
5. Der Upload-Fortschritt wird nach jedem bestätigten Paket gespeichert.

Die Workflow-Ausführung ist auf 15 Minuten begrenzt. Bei einem
ThingsBoard-Fehler wird der aktuelle Abrufstatus trotzdem veröffentlicht;
der betroffene Upload wird beim nächsten Lauf erneut versucht.

## ThingsBoard-Konfiguration

In den Repository-Einstellungen sind erforderlich:

- Repository-Variable `THINGSBOARD_URL`, zum Beispiel
  `https://eu.thingsboard.cloud`
- Repository-Secret `MESSSTELLE_1` mit dem Device Access Token

Die Workflow-Ausgabe verbindet das Secret über `THINGSBOARD_TOKEN` mit der
Messreihe aus [`measurement-series.json`](measurement-series.json). Weitere
Geräte benötigen einen zusätzlichen Eintrag in der Messreihen-Konfiguration
sowie das passende GitHub Secret.

Zugangsdaten dürfen nicht in Dateien, Diagrammen oder der HTML-Anzeige
gespeichert werden.

## Lokal ausführen

Die Tests werden ausgeführt mit:

```powershell
py -m unittest discover -s tests
```

Die Daten werden lokal aktualisiert mit:

```powershell
py scripts/sync_groundwater.py fetch groundwater-sync-state.json groundwater-data.json measurement-series.json
```

Die Übertragung an ThingsBoard benötigt Umgebungsvariablen:

```powershell
$env:THINGSBOARD_URL = "https://eu.thingsboard.cloud"
$env:THINGSBOARD_TOKEN = "<Device-Access-Token>"
py scripts/sync_groundwater.py upload groundwater-sync-state.json groundwater-data.json measurement-series.json
```

Lokale Ausführung ist nicht erforderlich, da der Workflow die Aktualisierung
automatisch in GitHub Actions übernimmt.

## Hinweis zur Dashboard-Einrichtung

Die HTML-Anzeige dient als Datensicherung und Visualisierung. Sie erzeugt
keine ThingsBoard-Telemetrie. Für ein ThingsBoard-Dashboard muss das richtige
Gerät mit dem Telemetrie-Schlüssel `groundwater_level` bestätigt und
historische Telemetrie geprüft werden. Vor einer vollständigen historischen
Übertragung sollte ein einzelner Messpunkt getestet werden.
