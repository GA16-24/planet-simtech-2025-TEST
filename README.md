# Blautopf-Wärmeschleuse

Wissenschaftlicher Lösungsentwurf für die PlaNeT-SimTech-Aufgabe 2025/26. Das Repository enthält ausschließlich den deutschsprachigen Bericht und das reproduzierbare Wärmemodell. Die Präsentation erstellt das menschliche Team separat.

## Ergebnis

Die Wärmeschleuse entnimmt erhitztes Karstwasser über Brunnen vor dem Quelltopf, kühlt es in einer Kaskade aus Wärmenutzung, Trockenkühlung und mechanischer Nachkühlung und speist dieselbe Wassermenge wieder in den Zufluss ein. Der Auslegungsfall folgt wörtlich dem linearen Temperaturanstieg auf 98,3 °C in zehn Jahren. Bei maximalem Abfluss sind 11,77 GW abzuführen. Das normale Ziel sind 9,5 °C, die technische Obergrenze liegt bei 12 °C. Der Quelltopf selbst bleibt ohne technische Einbauten.

160 Module liefern 12,8 GW, nach dem Ausfall eines Moduls bleiben 12,72 GW. Ein zweiter Rechenpfad berücksichtigt den weiteren Temperaturanstieg und den Ausbau auf 321 Module bis Jahr 20. Nach einem Ausfall bleiben auch dann 25,6 GW und damit 5,4 % Reserve. Eine einmal gebaute Anlage kann einen unbegrenzten Anstieg nicht für immer ausgleichen. Dafür ist ein 250-Mio.-€-Prüfpfad zur Quellbegrenzung enthalten. Alternative A mit fester Wärmeleistung bleibt als separates Szenario ohne Flüssigkeitsauslegung nach Siedebeginn erhalten.

## Dateien

- `report/bericht.html`: bearbeitbare Berichtsquelle.
- `report/TEST-0000.pdf`: erzeugte PDF mit Test-ID.
- `report/build_pdf.py`: PDF-Erzeugung und Formprüfung.
- `src/model.py`: Wärmebilanz, Hydraulik, Regelung, Monatsrechnung und Wirtschaftlichkeit.
- `build/`: erzeugte CSV-Dateien, Kennwerte und SVG-Abbildungen.
- `quellen.md`: Rechercheumfang und fachliche Quellen.

## Rechnung wiederholen

Python 3 genügt. Das Modell benötigt keine externen Python-Pakete.

```bash
python3 src/model.py --output-dir build
```

Das Programm prüft Zeitgrenzen, Wärme- und Massenbilanzen, Brunnenreserve, Ersatzkosten und Jahresstunden. Es erzeugt `verlauf.csv`, `monate.csv`, `monate-mittel.csv`, `monate-niedrig.csv`, `monate-waermeleistung.csv`, `ausbau.csv`, `konstant.csv`, `ausbau-waermeleistung.csv`, `kennwerte.json` und drei SVG-Dateien neu.

## Bericht erzeugen

Die PDF-Fassung wird mit WeasyPrint aus HTML erzeugt. Die Abhängigkeiten stehen in `requirements-report.txt`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-report.txt
.venv/bin/python report/build_pdf.py --team-id TEST-0000
```

Das Skript erwartet 15 Seiten: ein Deckblatt, zehn Hauptseiten, zwei Literatur- und Rechenseiten sowie zwei Anhangsseiten. Es prüft zentrale Textstellen und rendert alle Seiten zur visuellen Kontrolle nach `build/seiten/`.

## Vor einer echten Einreichung

TEST-0000 auf dem Deckblatt und im PDF-Dateinamen durch die echte Team-ID ersetzen. Das Team muss alle Annahmen, Rechnungen und Texte selbst prüfen und die KI-Nutzung nach den aktuellen Wettbewerbsregeln kenntlich machen. Dieses Repository reicht nichts ein.

Frühere Lösungen oder Siegerberichte des Wettbewerbs wurden nicht verwendet. Die Ideen und Herleitungen entstanden aus der Aufgabenstellung, den öffentlich zitierten Fachquellen und dem eigenen Modell.
