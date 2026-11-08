#!/usr/bin/env python3
import argparse
from pathlib import Path

import fitz
from pypdf import PdfReader
from weasyprint import HTML

parser = argparse.ArgumentParser()
parser.add_argument("--team-id", default="TEST-0000")
parser.add_argument("--language", choices=("de", "en"), default="de")
args = parser.parse_args()
if not args.team_id.replace("-", "").isalnum():
    raise SystemExit("The team ID may contain only letters, digits, and hyphens.")

ROOT = Path(__file__).resolve().parents[1]
languages = {
    "de": {
        "source": "bericht.html",
        "suffix": "",
        "render_dir": "seiten",
        "required": {
            0: [args.team_id, "PlaNeT SimTech"],
            1: ["Zusammenfassung", "11,77"],
            10: ["Schlussfolgerung"],
            11: ["Literaturverzeichnis"],
            13: ["Anhang", "Reproduktion"],
        },
    },
    "en": {
        "source": "report.html",
        "suffix": "-en",
        "render_dir": "pages-en",
        "required": {
            0: [args.team_id, "PlaNeT SimTech"],
            1: ["Summary", "11.77"],
            10: ["Conclusion"],
            11: ["References"],
            13: ["Appendix", "Reproduction"],
        },
    },
}
config = languages[args.language]
source = ROOT / "report" / config["source"]
target = ROOT / "report" / f"{args.team_id}{config['suffix']}.pdf"
html = source.read_text(encoding="utf-8").replace("TEST-0000", args.team_id)
HTML(string=html, base_url=str(ROOT)).write_pdf(str(target))
reader = PdfReader(str(target))
if len(reader.pages) != 15:
    raise SystemExit(f"Expected 15 PDF pages, found {len(reader.pages)}")

texts = [(page.extract_text() or "") for page in reader.pages]
for page_number, needles in config["required"].items():
    for needle in needles:
        if needle not in texts[page_number]:
            raise SystemExit(f"Page {page_number + 1}: '{needle}' is missing")

render_dir = ROOT / "build" / config["render_dir"]
render_dir.mkdir(parents=True, exist_ok=True)
document = fitz.open(target)
for index, page in enumerate(document):
    page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False).save(
        render_dir / f"page-{index + 1:02d}.png"
    )
print(f"PDF checked: {len(reader.pages)} pages, {target}")
