import re
import fitz

DATE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
TIME = re.compile(r"^\d{1,2}:\d{2}$")
ROLE = re.compile(r"^(Árbitr[oa]|2º Árbitro|A\. Asistente [12]|AA\. Cronometrador|Oficial Informador|Delegado Informador|Cronometrador)\s*:\s*(.*)$", re.I)
COMP = re.compile(r"^Competición:\s*(.+)$", re.I)

def parse(data):
    doc = fitz.open(stream=data, filetype="pdf")
    games, competitions, warnings = [], set(), []
    for page_num, page in enumerate(doc, 1):
        lines = [line.strip() for line in page.get_text("text", sort=False).splitlines() if line.strip()]
        competition = next((m.group(1).strip() for line in lines if (m := COMP.match(line))), None)
        if not competition:
            warnings.append("Falta competición en página " + str(page_num))
            continue
        competitions.add(competition)
        i = 0
        while i < len(lines):
            if not DATE.fullmatch(lines[i]):
                i += 1
                continue
            if i + 3 >= len(lines) or not TIME.fullmatch(lines[i + 3]):
                warnings.append("Partido no reconocido en página " + str(page_num))
                i += 1
                continue
            game = {"competition": competition, "date": lines[i], "home": lines[i+1], "away": lines[i+2], "time": lines[i+3], "page": page_num, "officials": {}}
            i += 4
            while i < len(lines) and not DATE.fullmatch(lines[i]):
                m = ROLE.match(lines[i])
                if m:
                    game["officials"][m.group(1).strip()] = m.group(2).strip()
                i += 1
            games.append(game)
    if not competitions or len(games) < 1:
        raise ValueError("El PDF no contiene partidos identificables por competición.")
    return {"games": games, "competitions": sorted(competitions), "pages": len(doc), "warnings": warnings}
