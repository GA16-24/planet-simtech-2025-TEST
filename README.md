# Blautopf heat-extraction circuit

Scientific design proposal for the PlaNeT SimTech task 2025/26. The repository contains the German report, an English translation, and the reproducible thermal model. The human team prepares the presentation separately.

## Results

The heat-extraction circuit draws heated karst water from wells upstream of the spring basin, cools it through heat recovery, dry cooling, and mechanical trim cooling, then returns the same quantity of water to the inflow. The design case follows the stated linear temperature rise to 98.3 °C over ten years. At maximum discharge, 11.77 GW of heat must be removed. The normal target is 9.5 °C, with a technical upper limit of 12 °C. No equipment is installed in the spring basin itself.

The 160 modules provide 12.8 GW. One module failure leaves 12.72 GW. A second calculation path accounts for continued warming and expansion to 321 modules by year 20. One failure then leaves 25.6 GW, a reserve of 5.4%. A fixed system cannot offset unlimited warming forever. The proposal therefore includes a €250 million assessment path for controlling the heat source. Alternative A, with fixed heat input, remains a separate scenario without liquid-water design after boiling begins.

## Files

- `report/bericht.html`: editable German report source.
- `report/TEST-0000.pdf`: generated German PDF with test ID.
- `report/report.html`: editable English report source.
- `report/TEST-0000-en.pdf`: generated English PDF with test ID.
- `report/build_pdf.py`: PDF generation and format checks for both languages.
- `src/model.py`: heat balance, hydraulics, control, monthly calculations, and economics.
- `build/`: generated CSV files, metrics, and German and English SVG figures.
- `quellen.md`: research scope and technical sources in German.

## Run the calculation

Python 3 is sufficient. The model requires no external Python packages.

```bash
python3 src/model.py --output-dir build
```

The program checks time limits, heat and mass balances, well reserve, replacement costs, and annual hours. It regenerates `verlauf.csv`, `monate.csv`, `monate-mittel.csv`, `monate-niedrig.csv`, `monate-waermeleistung.csv`, `ausbau.csv`, `konstant.csv`, `ausbau-waermeleistung.csv`, `kennwerte.json`, and six SVG files.

## Build the reports

WeasyPrint generates the PDFs from HTML. Dependencies are listed in `requirements-report.txt`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-report.txt
.venv/bin/python report/build_pdf.py --team-id TEST-0000
.venv/bin/python report/build_pdf.py --team-id TEST-0000 --language en
```

Each report must have 15 pages: one cover, ten main pages, two pages of references and calculations, and two appendices. The script checks key text on those pages and renders every page for visual inspection. German page images go to `build/seiten/`, English images to `build/pages-en/`.

## Before an actual submission

Replace TEST-0000 on the cover and in the PDF filename with the actual team ID by passing `--team-id`. The team must check all assumptions, calculations, and text itself and disclose AI use according to the current competition rules. This repository does not submit anything.

No earlier solutions or winning reports were used. The ideas and derivations come from the problem statement, the cited public technical sources, and the model in this repository.
