#!/usr/bin/env python3
import argparse
from pathlib import Path

import fitz
from pypdf import PdfReader
from weasyprint import HTML

parser = argparse.ArgumentParser()
parser.add_argument("--team-id", default="TEST-0000")
args = parser.parse_args()
if not args.team_id.replace("-", "").isalnum():
    raise SystemExit("Die Team-ID darf nur Buchstaben, Ziffern und Bindestriche enthalten.")

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "report" / "bericht.html"
target = ROOT / "report" / f"{args.team_id}.pdf"
html = source.read_text(encoding="utf-8").replace("TEST-0000", args.team_id)
HTML(string=html, base_url=str(ROOT)).write_pdf(str(target))
reader = PdfReader(str(target))
if len(reader.pages) != 15:
    raise SystemExit(f"Erwartet: 15 PDF-Seiten, gefunden: {len(reader.pages)}")

texts = [(page.extract_text() or "") for page in reader.pages]
required = {
    0: [args.team_id, "PlaNeT SimTech"],
    1: ["Zusammenfassung", "843"],
    10: ["Schlussfolgerung"],
    11: ["Literaturverzeichnis"],
    13: ["Anhang", "Reproduktion"],
}
for page_number, needles in required.items():
    for needle in needles:
        if needle not in texts[page_number]:
            raise SystemExit(f"Seite {page_number + 1}: '{needle}' fehlt")

render_dir = ROOT / "build" / "seiten"
render_dir.mkdir(parents=True, exist_ok=True)
document = fitz.open(target)
for index, page in enumerate(document):
    page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False).save(
        render_dir / f"seite-{index + 1:02d}.png"
    )
print(f"PDF geprüft: {len(reader.pages)} Seiten, {target}")
