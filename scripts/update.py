import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import requests
import fitz

out = Path(__file__).resolve().parents[1] / "docs" / "data"
out.mkdir(parents=True, exist_ok=True)
DOC_ID = "1059902"
DOWNLOAD_URL = "https://www.rfiflp.com/pnfg/NBdd_DesDocumento?cod_primaria=3002150&cod_documento=" + DOC_ID + "&descargar=1"

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def read(p, default):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError): return default
def save(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_pdf():
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    response = session.get(DOWNLOAD_URL, timeout=40)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF-"):
        raise RuntimeError("El enlace de descarga del documento 1059902 no devolvió un PDF.")
    if len(response.content) > 25_000_000: raise RuntimeError("PDF superior a 25 MB.")
    pdf = fitz.open(stream=response.content, filetype="pdf")
    if pdf.needs_pass: raise RuntimeError("PDF protegido.")
    pages = [{"page":i+1, "text":p.get_text("text", sort=True)} for i,p in enumerate(pdf)]
    full_text = "\n".join(p["text"] for p in pages).lower()
    # Rechazar documentos jurídicos o de gobierno y otros PDF que no sean designaciones.
    has_designations = any(word in full_text for word in ("designaciones arbitrales", "designación arbitral", "designaciones", "árbitro principal", "arbitro principal"))
    has_matches = any(word in full_text for word in ("local", "visitante", "encuentro", "partido", "competición", "competicion"))
    if not (has_designations and has_matches):
        raise RuntimeError("El PDF recibido no parece contener designaciones arbitrales; se descarta.")
    return response.content, response.url, pages

def main():
    status_file = out / "status.json"
    index_file = out / "index.json"
    old = read(status_file, {})
    status = {**old, "state":"pending", "checked_at":now(), "interval_minutes":30}
    try:
        content, url, pages = fetch_pdf()
        digest = hashlib.sha256(content).hexdigest()
        if digest != old.get("sha256") or not index_file.exists():
            save(index_file, {"sha256":digest, "source_url":url,"document_id":DOC_ID,"pages":pages})
            history_file = out / "history.json"
            history = read(history_file, [])
            history.insert(0, {"sha256":digest,"indexed_at":now(),"pages":len(pages)})
            save(history_file, history[:100])
            status.update({"sha256":digest,"updated_at":now(),"page_count":len(pages)})
        status.update({"state":"ok","error":None})
    except Exception as exc:
        status.update({"state":"error","error":str(exc)})
        print("Descarga o validación pendiente:", exc)
    save(status_file, status)
if __name__ == "__main__": main()
