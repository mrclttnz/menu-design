"""Cartella `dist` di prova per i test dei file statici (SL-01). Solo dati sintetici.

Non è la build reale: contiene i file che servono a provare allow-list, cache e traversal.
Fuori dalla cartella (in `<root>/`) ci sono file "canarino" che non devono mai essere serviti.
"""

from pathlib import Path

ASSET_JS = "/assets/index-Ab12Cd34.js"
ASSET_CSS = "/assets/index-Ef56Gh78.css"

INDEX_HTML = (
    '<!doctype html><html lang="it"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    "<title>Menu Design</title>"
    f'<script type="module" crossorigin src="{ASSET_JS}"></script>'
    f'<link rel="stylesheet" crossorigin href="{ASSET_CSS}">'
    '</head><body><div id="root"></div></body></html>'
)


def build_dist(root: Path, *, with_sw: bool = True) -> Path:
    """Crea `<root>/dist` e un file canarino in `<root>/outside.*`; restituisce `dist`."""
    dist = root / "dist"
    assets = dist / "assets"
    (assets / "subdir").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    if with_sw:
        (dist / "sw.js").write_text("self.addEventListener('install', () => {});\n")
    # JS comprimibile e più grande della soglia minima dei middleware gzip (500 byte).
    (assets / "index-Ab12Cd34.js").write_text("console.log('menu design');\n" * 200)
    (assets / "index-Ab12Cd34.js.map").write_text('{"version":3,"sourceMappingURL":"x"}')
    (assets / "index-Ef56Gh78.css").write_text("body{margin:0}\n" * 100)
    (assets / "index-Ef56Gh78.css.map").write_text('{"version":3}')
    (assets / "plain.js").write_text("console.log('no hash in the name');\n")
    (assets / "subdir" / "inner-Aa1Bb2Cc.js").write_text("console.log('nested');\n")
    (assets / ".env").write_text("SECRET=CANARY-STATIC-DOTENV\n")
    (dist / "notes.txt").write_text("CANARY-STATIC-NOTES\n")
    (dist / ".env").write_text("SECRET=CANARY-STATIC-DOTENV\n")
    (dist / ".hidden").mkdir()
    (dist / ".hidden" / "secret.txt").write_text("CANARY-STATIC-DOTENV\n")
    (root / "outside.js").write_text("CANARY-OUTSIDE-JS\n")
    (root / "outside.txt").write_text("CANARY-OUTSIDE-TXT\n")
    (assets / "link-Qq1Ww2Ee.js").symlink_to(root / "outside.js")
    return dist
