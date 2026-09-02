import re
import hashlib
from pathlib import Path
from datetime import datetime
from pypdf import PdfReader

USI_RE = re.compile(r"\b(?:USI|PRE)\d{6}\b", re.IGNORECASE)
CNC_RE = re.compile(r"\bCNC-[A-Z]{2,4}-\d{3,}\b", re.IGNORECASE)

PDF_EXTS = {".pdf"}
STEP_EXTS = {".step", ".stp"}
DRAWING_EXTS = {".slddrw", ".dwg", ".dxf"}
PART_EXTS = {".sldprt"}
NC_EXTS = {".nc"}

def _newest(paths):
    paths = [p for p in paths if p.exists()]
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None

def _fmt(path):
    if not path:
        return "-"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")

def _content_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def _inventory_item(path: Path, kind: str, folder: Path):
    st = path.stat()
    return {
        "file_path": str(path),
        "folder_path": str(folder),
        "file_kind": kind,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "sha256": _content_hash(path),
    }

def _signature(paths):
    values = []
    for p in sorted(paths, key=lambda x: str(x).lower()):
        try:
            st = p.stat()
            values.append(f"{p}|{st.st_size}|{st.st_mtime_ns}")
        except OSError:
            values.append(f"{p}|missing")
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()

def _unique(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out

def expected_folder_name(codes):
    return " - ".join(codes)

def valid_folder_name(folder_name, codes):
    if not codes:
        return False
    # Regra: somente códigos USI separados por " - ", sem descrição.
    normalized = re.sub(r"\s+", " ", folder_name.strip().upper())
    return normalized == expected_folder_name(codes)

def read_pdf_metadata(pdf_path):
    result = {
        "file": pdf_path.name,
        "text_ok": False,
        "codes": [],
        "cnc_codes": [],
        "internal_machining": False,
        "error": None,
    }
    try:
        reader = PdfReader(str(pdf_path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        result["text_ok"] = bool(text.strip())
        result["codes"] = _unique([x.upper() for x in USI_RE.findall(text)])
        # Accept legacy/internal drawing order DTS-CNC-RT-001 and normalize it.
        cnc = [x.upper() for x in CNC_RE.findall(text)]
        flexible = re.findall(
            r"\bCNC\s*[-–—]?\s*([A-Z]{2,4})\s*[-–—]?\s*(\d{3,})\b",
            text, flags=re.IGNORECASE
        )
        legacy = re.findall(
            r"\bDTS\s*[-–—]?\s*CNC\s*[-–—]?\s*([A-Z]{2,4})\s*[-–—]?\s*(\d{3,})\b",
            text, flags=re.IGNORECASE
        )
        normalized = [f"CNC-{a.upper()}-{n}" for a,n in flexible + legacy]
        result["cnc_codes"] = _unique(cnc + normalized)
        result["internal_machining"] = bool(re.search(r"Usinagem\s+Interna", text, re.IGNORECASE))
    except Exception as e:
        result["error"] = str(e)
    return result

def expected_datasheet_name(cnc_code):
    return f"{cnc_code}-DTS.pdf" if cnc_code else None

def analyze_folder(folder: Path):
    direct_files = [p for p in folder.iterdir() if p.is_file()]
    subdirs = [p for p in folder.iterdir() if p.is_dir()]

    pdfs = [p for p in direct_files if p.suffix.lower() in PDF_EXTS]
    steps = [p for p in direct_files if p.suffix.lower() in STEP_EXTS]
    drawings = [p for p in direct_files if p.suffix.lower() in DRAWING_EXTS]
    parts = [p for p in direct_files if p.suffix.lower() in PART_EXTS]

    machining_dirs = [
        p for p in subdirs
        if "usin" in p.name.lower()
        or p.name.lower() in {"cnc", "nc", "arquivos nc", "arquivos de usinagem"}
    ]

    ncs = []
    for d in machining_dirs:
        ncs += [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in NC_EXTS]

    codes = _unique([x.upper() for x in USI_RE.findall(folder.name)])
    folder_pattern_ok = valid_folder_name(folder.name, codes)
    folder_expected = expected_folder_name(codes) if codes else "Somente código(s) USI"

    problems = []
    actions = []
    categories = []

    def issue(category, problem, action):
        problems.append(problem)
        actions.append(action)
        categories.append(category)

    if not folder_pattern_ok:
        if codes:
            issue("estrutura", "Nome da pasta fora do padrão de produção",
                  f"A pasta de produção deve conter somente código(s) USI/PRE. Padrão identificado/esperado: {folder_expected}")
        else:
            issue("estrutura", "Pasta sem código de produção USI/PRE — requer avaliação",
                  "Avaliar esta pasta. No fluxo atual, somente pastas identificadas por código USI ou PRE são consideradas estrutura válida de produção.")

    if not pdfs:
        issue("arquivo", "Datasheet PDF ausente",
              "Adicionar o datasheet PDF na pasta principal.")
    if not drawings:
        issue("arquivo", "2D editável ausente",
              "Adicionar o desenho 2D editável (.SLDDRW, .DWG ou .DXF).")
    if not steps:
        issue("arquivo", "STEP/STP ausente",
              "Adicionar o arquivo STEP/STP na pasta principal.")
    if not parts:
        issue("arquivo", "Peça editável SLDPRT ausente",
              "Adicionar o arquivo editável da peça (.SLDPRT).")
    if not machining_dirs:
        issue("arquivo", "Subpasta de usinagem ausente",
              "Criar/adicionar a subpasta destinada aos arquivos de usinagem.")
    elif not ncs:
        issue("arquivo", "Arquivo .NC ausente na subpasta de usinagem",
              "Adicionar o(s) programa(s) .NC correspondente(s) na subpasta de usinagem.")

    # Read all PDFs and choose datasheet candidates that contain CNC/USI/process information.
    pdf_meta = [read_pdf_metadata(p) for p in pdfs]
    candidates = [m for m in pdf_meta if m["cnc_codes"] or m["codes"] or m["internal_machining"]]
    datasheet = candidates[0] if candidates else (pdf_meta[0] if pdf_meta else None)

    datasheet_codes = datasheet["codes"] if datasheet else []
    cnc_codes = datasheet["cnc_codes"] if datasheet else []
    cnc_code = cnc_codes[0] if cnc_codes else None
    process_ok = bool(datasheet and datasheet["internal_machining"])

    if datasheet:
        if not datasheet["text_ok"]:
            issue("documental", "Não foi possível ler o conteúdo textual do datasheet",
                  "Verificar se o PDF é pesquisável/vetorial e se corresponde ao datasheet correto.")
        else:
            if codes and set(datasheet_codes) != set(codes):
                issue("avaliacao",
                      "Divergência entre códigos da pasta e do datasheet — requer avaliação",
                      f"Verificar qual relação está correta. Pasta: {', '.join(codes) or '-'} | Datasheet: {', '.join(datasheet_codes) or '-'}. Ambos devem conter o mesmo conjunto de códigos, independentemente da ordem.")
            elif not codes and datasheet_codes:
                issue("avaliacao",
                      "Datasheet contém código(s) USI/PRE, mas o nome da pasta não",
                      f"O datasheet referencia: {', '.join(datasheet_codes)}. Avaliar se a pasta deveria ser identificada por esses códigos para integrar a estrutura de produção.")
            if not process_ok:
                issue("documental", "Processo 'Usinagem Interna' não identificado no datasheet",
                      "Verificar/corrigir o campo de processo do datasheet.")
            if not cnc_code:
                issue("documental", "Código CNC não identificado no datasheet",
                      "Verificar se o datasheet possui código no padrão CNC-RT-001.")
            else:
                expected_pdf = expected_datasheet_name(cnc_code)
                if datasheet["file"].upper() != expected_pdf.upper():
                    issue("padrao_arquivo",
                          "Nome do datasheet fora do padrão",
                          f"Renomear o PDF para: {expected_pdf}")
    else:
        expected_pdf = None

    # CNC correspondence: NC filename should reference the datasheet CNC root when possible.
    nc_match = None
    if cnc_code and ncs:
        nc_match = any(cnc_code.upper() in p.stem.upper() for p in ncs)
        if not nc_match:
            issue("cnc",
                  "Nenhum arquivo .NC corresponde ao código CNC do datasheet",
                  f"Verificar se os arquivos de usinagem correspondem ao código {cnc_code}.")

    newest_step = _newest(steps)
    newest_nc = _newest(ncs)
    date_issue = False
    if newest_step and newest_nc and newest_nc.stat().st_mtime < newest_step.stat().st_mtime:
        date_issue = True
        issue("temporal",
              "NC anterior ao STEP — possível alteração após programação",
              "Investigar se a alteração do STEP impacta a usinagem. Se não houver impacto, validar manualmente como OK.")

    tracked = pdfs + drawings + steps + parts + ncs
    file_inventory = []
    for p in pdfs:
        file_inventory.append(_inventory_item(p, "PDF", folder))
    for p in drawings:
        file_inventory.append(_inventory_item(p, "2D_EDITAVEL", folder))
    for p in steps:
        file_inventory.append(_inventory_item(p, "STEP", folder))
    for p in parts:
        file_inventory.append(_inventory_item(p, "PECA_EDITAVEL", folder))
    for p in ncs:
        file_inventory.append(_inventory_item(p, "NC", folder))
    status = "conforme"
    if problems:
        # Any missing file or structural/document mismatch is incomplete;
        # pure temporal/naming review can be attention.
        critical_categories = {"arquivo", "documental", "cnc"}
        status = "incompleto" if any(c in critical_categories for c in categories) else "atencao"

    rename_suggestions = []

    # V0.7.3.2 — regra conservadora também para Usinagem:
    # somente sugerir renomeação quando existe exatamente um código
    # concreto e inequívoco no padrão USI/PRE + 6 dígitos.
    concrete_codes = [
        str(c).strip().upper()
        for c in (codes or [])
        if re.fullmatch(r"(?:USI|PRE)\d{6}", str(c).strip().upper())
    ]

    if not folder_pattern_ok and len(concrete_codes) == 1:
        concrete_code = concrete_codes[0]
        rename_suggestions.append({
            "kind": "folder",
            "label": "Nome da pasta",
            "current_name": folder.name,
            "expected_name": concrete_code,
            "source_path": str(folder),
        })

    # O nome do datasheet só é sugerido quando o código CNC foi
    # efetivamente identificado. Nunca usar máscara ou código inferido.
    if datasheet and cnc_code:
        cnc_code = str(cnc_code).strip().upper()
        if re.fullmatch(r"CNC-RT-\d{3}", cnc_code):
            expected_pdf_name = expected_datasheet_name(cnc_code)
            if datasheet["file"].upper() != expected_pdf_name.upper():
                source_pdf = next((p for p in pdfs if p.name == datasheet["file"]), None)
                if source_pdf:
                    rename_suggestions.append({
                        "kind": "file",
                        "label": "Nome do datasheet",
                        "current_name": source_pdf.name,
                        "expected_name": expected_pdf_name,
                        "source_path": str(source_pdf),
                    })

    return {
        "folder_name": folder.name,
        "folder_path": str(folder),
        "codes": codes,
        "folder_pattern_ok": folder_pattern_ok,
        "folder_expected": folder_expected,
        "pdf": bool(pdfs),
        "drawing": bool(drawings),
        "step": bool(steps),
        "part": bool(parts),
        "machining_dir": bool(machining_dirs),
        "nc": bool(ncs),
        "datasheet_file": datasheet["file"] if datasheet else None,
        "datasheet_codes": datasheet_codes,
        "cnc_code": cnc_code,
        "process_ok": process_ok,
        "expected_datasheet": expected_datasheet_name(cnc_code),
        "nc_cnc_match": nc_match,
        "step_date": _fmt(newest_step),
        "nc_date": _fmt(newest_nc),
        "status": status,
        "problems": problems,
        "actions": actions,
        "categories": categories,
        "adjustment_count": len(actions),
        "rename_suggestions": rename_suggestions,
        "signature": _signature(tracked),
        "file_inventory": file_inventory,
    }

def scan_root(root_path: str):
    root = Path(root_path)
    if not root.is_dir():
        raise ValueError("Pasta não encontrada.")

    results = []
    for folder in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda x: x.name.lower()):
        results.append(analyze_folder(folder))

    # V0.7.3: investigação obrigatória de duplicidade do código CNC do datasheet.
    occurrences = {}
    for r in results:
        cnc = (r.get("cnc_code") or "").strip().upper()
        if cnc:
            occurrences.setdefault(cnc, []).append(r)

    for cnc, items in occurrences.items():
        if len(items) < 2:
            continue
        locations = [x.get("folder_name", "") for x in items]
        detail = " | ".join(locations)
        for r in items:
            r.setdefault("problems", []).append(f"Código CNC duplicado: {cnc}-DTS")
            r.setdefault("actions", []).append(
                f"Investigar a duplicidade antes de qualquer renomeação. Ocorrências: {detail}"
            )
            r.setdefault("categories", []).append("duplicidade_cnc")
            r["adjustment_count"] = len(r.get("actions") or [])
            r["status"] = "incompleto"
            r["cnc_duplicate"] = True
            r["cnc_duplicate_locations"] = locations
    return results
