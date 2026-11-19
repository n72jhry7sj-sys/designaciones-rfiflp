"""Importa de forma gradual actas públicas RFIFLP.

El reconocimiento de tarjeta exige una señal explícita en el HTML
(tipo/color de imagen). Los encuentros no verificados quedan pendientes.
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
MANIFEST = DATA / "history_manifest.json"
REPORTS = DATA / "match_reports.json"
PROGRESS = DATA / "match_reports_progress.json"
BASE = "https://www.fiflp.com/pnfg/NPcd/NFG_CmpPartido"
BATCH = max(1, min(int(os.environ.get("ACTA_BATCH", "40")), 100))
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RFIFLP-designaciones/1.0; public match data)"}


def read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def candidates():
    seen = set()
    for part in read(MANIFEST, {}).get("parts", []):
        path = ROOT / "docs" / part.removeprefix("./")
        for match in read(path, {}).get("records", []):
            code = str(match.get("code", ""))
            if not code.isdigit() or code in seen:
                continue
            seen.add(code)
            yield code, match


def card_color(image):
    """Solo etiquetas explícitas, nunca deducir el color de 'Image'."""
    attrs = " ".join(str(image.get(x, "")) for x in ("alt", "title", "aria-label", "src", "data-original")).lower()
    if re.search(r"(?:amarill|yellow)", attrs):
        return "yellow"
    if re.search(r"(?:roj[ao]|red.?card)", attrs):
        return "red"
    return None


def inspect(html, match):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if "Ficha de Partido" not in text or "Tarjetas" not in text:
        return None, "Sin ficha completa o sección Tarjetas"

    # Comprobar fecha antes de vincular una ficha: no aceptar páginas ajenas.
    expected = match["date"]
    day, month, year = expected.split("-")
    date_variants = (expected, f"{day}/{month}/{year}", f"{year}-{month}-{day}")
    if not any(x in text for x in date_variants):
        return None, "Fecha del acta no coincide: " + expected

    # Exigir fila de tarjeta con minuto; no contabilizar iconos de leyenda.
    explicit = {"yellow": 0, "red": 0}
    ambiguous = []
    for img in soup.find_all("img"):
        row = img.find_parent(["tr", "li"])
        if not row:
            continue
        row_text = row.get_text(" ", strip=True)
        if not re.search(r"\(\s*\d{1,3}\s*['’]\s*\)", row_text):
            continue
        heading = row.find_previous(re.compile(r"^h[1-6]$"))
        if heading is None or "tarjetas" not in heading.get_text(" ", strip=True).lower():
            continue
        color = card_color(img)
        if color:
            explicit[color] += 1
        else:
            ambiguous.append(str(img)[:130])
    if ambiguous:
        return None, "Hay iconos en filas de tarjetas cuyo color no se pudo clasificar"
    if not any(explicit.values()):
        return None, "No hay tarjetas de color verificable: no inferir cero desde el HTML"

    return {
        "validated": True,
        "yellow_cards_count": explicit["yellow"],
        "red_cards_count": explicit["red"],
        "cards_validation": "Colores explícitos en atributos de imágenes",
    }, None


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    reports = read(REPORTS, {})
    progress = read(PROGRESS, {"cursor": 0})
    games = list(candidates())
    if not games:
        raise RuntimeError("No hay códigos de acta en los históricos")
    initial = int(progress.get("cursor", 0)) % len(games)
    processed = verified = failures = 0
    sample_errors = []
    session = requests.Session()
    session.headers.update(HEADERS)
    for offset in range(min(BATCH, len(games))):
        code, match = games[(initial + offset) % len(games)]
        if reports.get(code, {}).get("validated") is True:
            continue
        processed += 1
        try:
            response = session.get(BASE, params={"CodActa": code, "cod_primaria": "1000120"}, timeout=15)
            response.raise_for_status()
            parsed, error = inspect(response.text, match)
            if parsed:
                reports[code] = {**reports.get(code, {}), **parsed, "official_url": response.url,
                                 "date": match["date"], "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                verified += 1
            elif len(sample_errors) < 5:
                sample_errors.append({"code": code, "reason": error})
        except requests.RequestException as exc:
            failures += 1
            if len(sample_errors) < 5:
                sample_errors.append({"code": code, "reason": str(exc)[:140]})
        time.sleep(0.25)
    progress = {"cursor": (initial + min(BATCH, len(games))) % len(games),
                "total_unique_games": len(games), "checked_this_run": processed,
                "verified_this_run": verified, "network_errors": failures,
                "verified_total": sum(r.get("validated") is True for r in reports.values()),
                "last_checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "samples": sample_errors}
    save(REPORTS, reports)
    save(PROGRESS, progress)
    print(json.dumps(progress, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
