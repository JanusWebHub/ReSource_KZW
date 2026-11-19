# Auftrag fuer ThingsBoard Copilot

Bitte untersuche und richte in meiner ThingsBoard-Cloud-Instanz die Anzeige der Grundwasser-Messreihe ein. Arbeite direkt in der aktuell verbundenen Instanz, soweit deine Berechtigungen das erlauben. Wenn eine Einstellung oder Information fehlt, frage mich danach, statt Werte zu erraten.

## Projekt

- Plattform: ThingsBoard Cloud, Host `eu.thingsboard.cloud`
- Messstelle: Messstelle 1, Reinickendorf, Berlin
- Einheit: `m ü. NHN`
- Erwarteter Telemetrie-Schluessel fuer den Messwert: `groundwater_level`
- Datenquelle: Wasserportal Berlin, Messstelle 1
- Im Projekt gibt es eine HTML-CSV-Anzeige, die den neuesten Wert und die 500 neuesten Messungen als Wert, Zeitreihe und Tabelle darstellt. Das soll im ThingsBoard-Dashboard moeglichst entsprechend abgebildet werden.

## Zuerst untersuchen

1. Finde das vorhandene ThingsBoard-Geraet fuer Messstelle 1. Falls es mehrere passende Geraete gibt, liste sie auf und frage, welches verwendet werden soll. Erstelle kein Duplikat ohne Rueckfrage.
2. Pruefe unter dem Geraet die Bereiche **Latest telemetry** und **Time series**. Stelle fest, welche Schluessel und Zeitstempel tatsaechlich gespeichert sind und ueber welchen Zeitraum historische Telemetrie vorhanden ist.
3. Pruefe das vorhandene Dashboard und seine Datenquellen, Zeitfenster und Widget-Typen. Aendere keine anderen Geraete oder Dashboards.
4. Beachte: Die aktuelle GitHub-Action sendet im wiederhergestellten Stand nur den neuesten Messwert als flaches JSON. Das Feld `measured_at` wird dabei als gewoehnlicher Telemetrie-Schluessel mitgesendet; es setzt nicht den Zeitstempel des Datenpunkts. Daher kann die derzeitige Action allein keine historische Messreihe aufbauen.
5. Ein vorheriger Versuch, die historische Messreihe als grosse Arrays von Zeitstempeln ueber den Device-HTTP-Endpunkt zu senden, endete bei ThingsBoard Cloud bereits fuer das erste Paket mit **HTTP 500**. Der CSV-Abruf funktionierte und fand etwa 12.641 Messpunkte. Bitte behaupte nicht, dass die Daten bereits importiert wurden.

## Fehlerursache pruefen

Pruefe, ob die bestehende Instanz bzw. API das Senden historischer Telemetrie mit Zeitstempeln unterstuetzt und welche Payload-Form sie akzeptiert. Nutze dafuer zuerst einen sicheren Test mit einem oder wenigen Testpunkten und bestaetige, dass diese unter **Time series** mit dem erwarteten Datum erscheinen.

Beispiel fuer einen einzelnen historischen Messpunkt:

```json
{
  "ts": 1762646400000,
  "values": {
    "groundwater_level": 33.41
  }
}
```

Der `ts`-Wert ist ein Unix-Zeitstempel in Millisekunden und muss aus dem echten Messdatum berechnet werden. Verwende keine Beispieldaten als echte Messung. Falls die API einen Fehler liefert, gib Statuscode und nicht geheime Antwortdetails aus. Token, Passwoerter und andere Zugangsdaten duerfen weder angezeigt noch in Notizen oder Widgets gespeichert werden.

Bitte sende nicht ungefragt erneut die gesamte Messreihe mit 12.641 Punkten. Erst nach erfolgreichem Kleinsttest einen geeigneten Importweg vorschlagen und mich vor einem vollstaendigen Import um Bestaetigung bitten. Bestehende Telemetrie nicht loeschen.

## Dashboard einrichten

Wenn das richtige Geraet und der Daten-Schluessel bestaetigt sind, richte ein Dashboard fuer die Messstelle ein oder aktualisiere das passende bestehende Dashboard:

1. **Neuester Messwert**: Wert- oder Karten-Widget fuer `groundwater_level`, Einheit `m ü. NHN`, mit Datum/Uhrzeit der letzten Messung, soweit verfuegbar.
2. **Zeitreihe**: Zeitreihen-/Liniendiagramm fuer `groundwater_level`, Zeitachse aus den Telemetrie-Zeitstempeln, beschriftet mit Messstelle und Einheit. Zeitraum soll vom Nutzer auf den gesamten vorhandenen Datenbereich erweitert werden koennen.
3. **Messwerttabelle**: Tabelle mit Messzeit und `groundwater_level`, neueste Messung zuerst. Wenn ein Widget die Begrenzung auf 500 Zeilen oder die Sortierung nicht unterstuetzt, erklaere die Grenze und richte die naechstpassende Ansicht ein, statt einen nicht vorhandenen Messwertbereich vorzutäuschen.
4. Widgets muessen an das bestaetigte Geraet bzw. dessen Alias gebunden sein und duerfen nicht auf zufaellige oder simulierte Daten zeigen.
5. Speichere das Dashboard und pruefe, ob es Daten anzeigt. Falls noch keine historische Telemetrie vorhanden ist, kennzeichne das klar und erklaere, dass die Dashboard-Konfiguration allein keine historischen Daten erzeugt.

## Abschlussbericht

Berichte knapp:

- welches Geraet verwendet wurde,
- welche Telemetrie-Schluessel und welcher Zeitbereich vorhanden waren,
- ob der historische Test erfolgreich war und mit welchem Zeitstempel,
- welche Widgets eingerichtet/geaendert wurden,
- was noch auf GitHub-Seite angepasst werden muss, damit kuenftige historische Messungen mit korrektem Zeitstempel ankommen.

## Sicherheits- und Aenderungsgrenzen

- Keine Tokens oder Zugangsdaten auslesen, anzeigen oder veraendern.
- Keine Geraete, Telemetrie, Dashboards oder Kundenkonten loeschen.
- Keine Daten aus anderen Messstellen veraendern.
- GitHub-Workflow oder Repository nicht bearbeiten; dieser Auftrag betrifft die ThingsBoard-Instanz.
- Bei unklarer Auswahl, destruktiver Aktion, Import grosser Datenmengen oder kostenrelevanter Einstellung vorab nachfragen.
