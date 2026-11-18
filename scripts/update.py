import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests, fitz
from bs4 import BeautifulSoup

out = Path(__file__).resolve().parents[1] / "docs" / "data"
out.mkdir(parents=True, exist_ok=True)
document = "https://www.rfiflp.com/pnfg/NBdd_ShwDocumento?cod_primaria=3002150&cod_documento=1059902"
hosts = {"www.rfiflp.com", "rfiflp.com"}

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def read(p, default):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError): return default
def save(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def download():
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    r = session.get(document, timeout=35)
    r.raise_for_status()
    if r.content.startswith(b"%PDF-"): return r.content, r.url
    if "text/html" not in r.headers.get("Content-Type", "").lower():
        raise RuntimeError("La respuesta no es un PDF.")
    soup = BeautifulSoup(r.content, "html.parser")
    for element in soup.select("a[href],iframe[src],embed[src],object[data]"):
        value = element.get("href") or element.get("src") or element.get("data")
        if not value: continue
        words = (value + " " + element.get_text(" ", strip=True)).lower()
        if not any(key in words for key in (".pdf", "descarg", "adjunto", "download")): continue
        url = urljoin(r.url, value)
        if urlparse(url).hostname not in hosts: continue
        result = session.get(url, timeout=35)
        result.raise_for_status()
        if result.content.startswith(b"%PDF-"): return result.content, result.url
    raise RuntimeError("No se encontró el PDF. Puede requerir una descarga dinámica.")

def main():
    status_file = out / "status.json"
    index_file = out / "index.json"
    old = read(status_file, {})
    status = {**old, "state":"pending", "checked_at":now(), "interval_minutes":30}
    try:
        data, url = download()
        if len(data) > 25_000_000: raise RuntimeError("PDF demasiado grande.")
        digest = hashlib.sha256(data).hexdigest()
        if digest != old.get("sha256") or not index_file.exists():
            pdf = fitz.open(stream=data, filetype="pdf")
            if pdf.needs_pass: raise RuntimeError("PDF protegido.")
            pages = [{"page":i+1, "text":p.get_text("text", sort=True)} for i,p in enumerate(pdf)]
            if not any(p["text"].strip() for p in pages): raise RuntimeError("PDF sin texto extraíble.")
            save(index_file, {"sha256":digest,"source_url":url,"pages":pages})
            history_file = out / "history.json"
            history = read(history_file, [])
            history.insert(0, {"sha256":digest,"indexed_at":now(),"pages":len(pages)})
            save(history_file, history[:100])
            status.update({"sha256":digest,"updated_at":now(),"page_count":len(pages)})
        status.update({"state":"ok","error":None})
    except Exception as exc:
        status.update({"state":"error","error":str(exc)})
        print("No se ha podido descargar el PDF:", exc)
    save(status_file, status)
if __name__ == "__main__": main()
