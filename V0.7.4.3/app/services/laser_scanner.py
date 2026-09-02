
import re
import hashlib
from pathlib import Path

CRT_RE = re.compile(r"\bCRT\d{6}\b", re.IGNORECASE)
ANY_CODE_RE = re.compile(r"\b(?:CRT|USI|PRE)\d{6}\b", re.IGNORECASE)
DXF_EXTS = {".dxf"}
PDF_EXTS = {".pdf"}

def _hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def analyze_laser_folder(folder: Path):
    files = [p for p in folder.iterdir() if p.is_file()]
    dxfs = [p for p in files if p.suffix.lower() in DXF_EXTS]
    pdfs = [p for p in files if p.suffix.lower() in PDF_EXTS]

    any_codes = [x.upper() for x in ANY_CODE_RE.findall(folder.name)]
    crt_codes = [x.upper() for x in CRT_RE.findall(folder.name)]

    expected = " - ".join(crt_codes) if crt_codes else "CRT######"
    normalized = re.sub(r"\s+", " ", folder.name.strip().upper())
    folder_pattern_ok = bool(crt_codes) and normalized == expected

    problems, actions, categories = [], [], []

    def issue(category, problem, action):
        categories.append(category)
        problems.append(problem)
        actions.append(action)

    if not crt_codes:
        if any_codes:
            issue(
                "estrutura",
                "Código fora do padrão do Corte a Laser",
                "Nesta pasta oficial de Corte a Laser, o código válido é CRT. Gerar/atribuir o código CRT correspondente e adequar o nome da pasta."
            )
        else:
            issue(
                "estrutura",
                "Pasta sem código CRT — requer avaliação",
                "Avaliar esta pasta. No fluxo atual do Corte a Laser, a estrutura válida de produção deve utilizar código CRT."
            )
    elif not folder_pattern_ok:
        issue(
            "estrutura",
            "Nome da pasta fora do padrão do Corte a Laser",
            f"A pasta deve conter somente o(s) código(s) CRT. Padrão esperado: {expected}"
        )

    if not dxfs:
        issue("arquivo", "Arquivo DXF ausente", "Adicionar o arquivo .DXF correspondente ao corte.")
    if not pdfs:
        issue("arquivo", "Datasheet PDF ausente", "Adicionar o datasheet PDF correspondente.")

    inventory = []
    for p in dxfs:
        st = p.stat()
        inventory.append({
            "file_path": str(p),
            "folder_path": str(folder),
            "file_kind": "DXF",
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "sha256": _hash(p),
        })
    for p in pdfs:
        st = p.stat()
        inventory.append({
            "file_path": str(p),
            "folder_path": str(folder),
            "file_kind": "PDF_LASER",
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "sha256": _hash(p),
        })

    signature = hashlib.sha256(
        "|".join(f"{x['file_path']}:{x['sha256']}" for x in inventory).encode("utf-8")
    ).hexdigest()

    return {
        "folder_name": folder.name,
        "folder_path": str(folder),
        "codes": crt_codes,
        "folder_pattern_ok": folder_pattern_ok,
        "folder_expected": expected,
        "dxf": bool(dxfs),
        "pdf": bool(pdfs),
        "status": "conforme" if not problems else "incompleto",
        "problems": problems,
        "actions": actions,
        "categories": categories,
        "adjustment_count": len(actions),
        "file_inventory": inventory,
        "signature": signature,
    }

def scan_laser_root(root_path: str):
    root = Path(root_path)
    if not root.is_dir():
        raise ValueError("Pasta de Corte a Laser não encontrada.")
    return [
        analyze_laser_folder(folder)
        for folder in sorted(
            (p for p in root.iterdir() if p.is_dir()),
            key=lambda p: p.name.lower()
        )
    ]
