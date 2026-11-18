import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import requests
import fitz
from parser import parse

out = Path(__file__).resolve().parents[1] / "docs" / "data"
out.mkdir(parents=True, exist_ok=True)
manual_pdf = Path(__file__).resolve().parents[1] / "docs" / "source" / "latest.pdf"
DOC_ID = "1059902"
DOWNLOAD_URL = "https://www.rfiflp.com/pnfg/NBdd_DesDocumento?cod_primaria=3002150&cod_documento=" + DOC_ID + "&descargar=1"

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def read(p, default):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError): return default
def save(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_pdf():
    if manual_pdf.exists():
        data = manual_pdf.read_bytes()
        if not data.startswith(b"%PDF-"): raise RuntimeError("El archivo adjuntado no es un PDF.")
        result = parse(data)
        return data, "Documento adjuntado al repositorio", result
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    response = session.get(DOWNLOAD_URL, timeout=40)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF-"):
        raise RuntimeError("El enlace de descarga del documento 1059902 no devolvió un PDF.")
    if len(response.content) > 25_000_000: raise RuntimeError("PDF superior a 25 MB.")
    pdf = fitz.open(stream=response.content, filetype="pdf")
    if pdf.needs_pass: raise RuntimeError("PDF protegido.")
    parsed = parse(response.content)
    return response.content, response.url, parsed

def main():
    status_file = out / "status.json"
    index_file = out / "index.json"
    old = read(status_file, {})
    status = {**old, "state":"pending", "checked_at":now(), "interval_minutes":30}
    try:
        content, url, parsed = fetch_pdf()
        digest = hashlib.sha256(content).hexdigest()
        if digest != old.get("sha256") or not index_file.exists():
            save(index_file, {"sha256":digest, "source_url":url,"document_id":DOC_ID, **parsed})
            history_file = out / "history.json"
            history = read(history_file, [])
            history.insert(0, {"sha256":digest,"indexed_at":now(),"pages":parsed["pages"]})
            save(history_file, history[:100])
            status.update({"sha256":digest,"updated_at":now(),"page_count":parsed["pages"], "game_count":len(parsed["games"]), "competition_count":len(parsed["competitions"])})
        status.update({"state":"ok","error":None})
    except Exception as exc:
        status.update({"state":"error","error":str(exc)})
        print("Descarga o validación pendiente:", exc)
    save(status_file, status)
if __name__ == "__main__": main()
