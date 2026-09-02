import hashlib
from datetime import datetime
from pathlib import Path
import os
import json
import re

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.database import get_conn
from app.services.scanner import scan_root
from app.services.product_structure import extract_text, parse_structure_text
from app.services.laser_scanner import scan_laser_root
from app.services.library_scanner import scan_library_root
from app.services.persistence import sync_file_evidence

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

def save_process_scan_snapshot(process_key, environment_name, folder_path, results, user_id, user_name):
    """
    Salva o resultado completo da última análise do processo.
    Isso permite reconstruir a tabela após qualquer recarga do dashboard,
    inclusive após atualizar/analisar uma Estrutura do Produto.
    """
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    payload = json.dumps(results, ensure_ascii=False, default=str)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO process_scan_snapshot
            (process_key,environment_name,folder_path,results_json,analyzed_at,analyzed_by,analyzed_by_name)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(process_key) DO UPDATE SET
                environment_name=excluded.environment_name,
                folder_path=excluded.folder_path,
                results_json=excluded.results_json,
                analyzed_at=excluded.analyzed_at,
                analyzed_by=excluded.analyzed_by,
                analyzed_by_name=excluded.analyzed_by_name
        """, (process_key, environment_name, folder_path, payload, now, user_id, user_name))


def get_process_scan_snapshot(process_key):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM process_scan_snapshot WHERE process_key=?",
            (process_key,)
        ).fetchone()

    if not row:
        return None

    try:
        results = json.loads(row["results_json"] or "[]")
    except Exception:
        results = []

    return {
        "process_key": process_key,
        "environment_name": row["environment_name"] or "",
        "folder_path": row["folder_path"] or "",
        "results": results,
        "analyzed_at": row["analyzed_at"],
    }


def save_process_summary(process_key, results, user_id, user_name):
    total = len(results)
    ok = sum(1 for r in results if r.get("status") == "conforme")
    warning = sum(1 for r in results if r.get("status") in ("atencao", "verificado"))
    bad = sum(1 for r in results if r.get("status") == "incompleto")
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO process_scan_summary
            (process_key,total,ok,warning,bad,analyzed_at,analyzed_by,analyzed_by_name)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(process_key) DO UPDATE SET
                total=excluded.total,
                ok=excluded.ok,
                warning=excluded.warning,
                bad=excluded.bad,
                analyzed_at=excluded.analyzed_at,
                analyzed_by=excluded.analyzed_by,
                analyzed_by_name=excluded.analyzed_by_name
        """, (process_key,total,ok,warning,bad,now,user_id,user_name))
    return {"total": total, "ok": ok, "warning": warning, "bad": bad, "analyzed_at": now}


def save_monitored_code_results(process_key, results):
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    rows = []
    for r in results:
        codes = r.get("codes") or []
        if isinstance(codes, str):
            codes = [codes]
        if not codes:
            codes = re.findall(r"\b(?:USI|PRE|CRT)\d{6}\b", r.get("folder_name", ""), flags=re.I)
        for code in codes:
            code = str(code).upper()
            if process_key == "usinagem" and not code.startswith(("USI", "PRE")):
                continue
            if process_key == "corte_laser" and not code.startswith("CRT"):
                continue
            rows.append((
                process_key, code, r.get("folder_name", ""), r.get("folder_path", ""),
                r.get("status", "incompleto"),
                json.dumps(r.get("problems") or [], ensure_ascii=False),
                json.dumps(r.get("actions") or [], ensure_ascii=False),
                r.get("signature", ""), now
            ))
    with get_conn() as conn:
        conn.execute("DELETE FROM monitored_code_results WHERE process_key=?", (process_key,))
        if rows:
            conn.executemany("""
                INSERT INTO monitored_code_results
                (process_key,code,folder_name,folder_path,status,problems_json,actions_json,signature,analyzed_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(process_key,code) DO UPDATE SET
                    folder_name=excluded.folder_name,
                    folder_path=excluded.folder_path,
                    status=excluded.status,
                    problems_json=excluded.problems_json,
                    actions_json=excluded.actions_json,
                    signature=excluded.signature,
                    analyzed_at=excluded.analyzed_at
            """, rows)


def get_structure_crosscheck(conn):
    monitored = conn.execute("SELECT * FROM monitored_code_results").fetchall()
    monitored_map = {(r["process_key"], r["code"]): dict(r) for r in monitored}
    items = conn.execute("""
        SELECT i.*, s.source_name
        FROM product_structure_items i
        JOIN product_structures s ON s.id=i.structure_id
        ORDER BY i.id DESC
    """).fetchall()
    snapshots = {
        "usinagem": get_process_scan_snapshot("usinagem"),
        "corte_laser": get_process_scan_snapshot("corte_laser"),
    }
    output=[]
    for row in items:
        item=dict(row)
        scope=item.get("evaluation_scope") or ""
        if scope=="Avaliar em Usinagem":
            process_key, process_name="usinagem","Usinagem Interna"
        elif scope=="Avaliar em Corte a Laser":
            process_key, process_name="corte_laser","Corte a Laser"
        else:
            process_key, process_name=None,"Não avaliado nesta versão"
        match=monitored_map.get((process_key,item["code"])) if process_key else None
        item["monitor_process"]=process_name
        item["found"]=bool(match)
        item["monitor_status"]=match["status"] if match else ("fora_escopo" if not process_key else "nao_encontrado")
        item["monitor_folder"]=match["folder_name"] if match else ""
        item["monitor_folder_path"]=match["folder_path"] if match else ""
        item["monitor_analyzed_at"]=match["analyzed_at"] if match else ""
        item["monitor_problems"]=json.loads(match["problems_json"] or "[]") if match else []
        item["monitor_actions"]=json.loads(match["actions_json"] or "[]") if match else []
        item["monitor_requirements"]={}
        if match and process_key:
            snap=snapshots.get(process_key)
            if snap:
                for r in snap.get("results") or []:
                    if item["code"] in (r.get("codes") or []):
                        if process_key=="usinagem":
                            item["monitor_requirements"]={
                                "Padrão da pasta":bool(r.get("folder_pattern_ok")),
                                "PDF":bool(r.get("pdf")),
                                "2D editável":bool(r.get("drawing")),
                                "STEP":bool(r.get("step")),
                                "Editável da peça":bool(r.get("part")),
                                "Pasta de usinagem":bool(r.get("machining_dir")),
                                ".NC":bool(r.get("nc")),
                            }
                        else:
                            item["monitor_requirements"]={
                                "Padrão da pasta":bool(r.get("folder_pattern_ok")),
                                "DXF":bool(r.get("dxf")),
                                "PDF":bool(r.get("pdf")),
                            }
                        break
        output.append(item)
    return output



def _parse_dt_br(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y %H:%M:%S")
    except Exception:
        return None


def summarize_structure_crosschecks(rows):
    grouped = {}
    for item in rows:
        sid = item.get("structure_id")
        key = sid if sid is not None else item.get("source_name")
        g = grouped.setdefault(key, {
            "structure_id": sid,
            "source_name": item.get("source_name") or "Estrutura",
            "total_codes": 0,
            "internal_codes": 0,
            "compliant_codes": 0,
            "incomplete_codes": 0,
            "missing_codes": 0,
            "external_codes": 0,
            "prepared_codes": 0,
            "overall_status": "SEM AVALIAÇÃO",
            "latest_monitor_at": None,
            "items": [],
        })
        g["items"].append(item)
        g["total_codes"] += 1

        if item.get("prefix") == "PRE":
            g["prepared_codes"] += 1
        if item.get("internal_external") == "Externo":
            g["external_codes"] += 1
        if item.get("internal_external") == "Interno":
            g["internal_codes"] += 1

        st = item.get("monitor_status")
        if st == "conforme":
            g["compliant_codes"] += 1
        elif st == "incompleto":
            g["incomplete_codes"] += 1
        elif st == "nao_encontrado":
            g["missing_codes"] += 1

        dt = _parse_dt_br(item.get("monitor_analyzed_at"))
        if dt and (g["latest_monitor_at"] is None or dt > g["latest_monitor_at"]):
            g["latest_monitor_at"] = dt

    for g in grouped.values():
        if g["missing_codes"] > 0:
            g["overall_status"] = "CÓDIGOS NÃO ENCONTRADOS"
        elif g["incomplete_codes"] > 0:
            g["overall_status"] = "PENDÊNCIAS"
        elif g["internal_codes"] > 0 and g["compliant_codes"] > 0:
            g["overall_status"] = "CONFORME"
        else:
            g["overall_status"] = "SEM AVALIAÇÃO"

        if g["latest_monitor_at"]:
            g["latest_monitor_at"] = g["latest_monitor_at"].strftime("%d/%m/%Y %H:%M:%S")

    return list(grouped.values())


def latest_structure_crosscheck_history(conn):
    rows = conn.execute("""
        SELECT h.*
        FROM structure_crosscheck_history h
        JOIN (
            SELECT structure_id, MAX(id) AS max_id
            FROM structure_crosscheck_history
            GROUP BY structure_id
        ) x ON x.max_id=h.id
    """).fetchall()
    return {r["structure_id"]: dict(r) for r in rows}

def require_user(request: Request):
    return request.session.get("user_id")

def audit(request: Request, action: str, details: str = ""):
    uid = request.session.get("user_id")
    name = request.session.get("user_name", "Usuário")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log(user_id,user_name,action,details,created_at) VALUES(?,?,?,?,?)",
            (uid, name, action, details, datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        )

@router.get("/dashboard")
def dashboard(request: Request):
    uid = require_user(request)
    if not uid:
        return RedirectResponse("/", status_code=303)

    with get_conn() as conn:
        settings = conn.execute("SELECT * FROM corporate_settings WHERE id=1").fetchone()
        process_envs = conn.execute("SELECT * FROM process_environments ORDER BY id").fetchall()
        summary_rows = conn.execute("SELECT * FROM process_scan_summary").fetchall()
        product_structures = conn.execute("""
            SELECT s.*,
                   COUNT(i.id) AS item_count
            FROM product_structures s
            LEFT JOIN product_structure_items i ON i.structure_id=s.id
            GROUP BY s.id
            ORDER BY s.id DESC
            LIMIT 50
        """).fetchall()
        product_structure_items = conn.execute("""
            SELECT i.*, s.source_name
            FROM product_structure_items i
            JOIN product_structures s ON s.id=i.structure_id
            ORDER BY i.id DESC LIMIT 500
        """).fetchall()
        structure_crosscheck = get_structure_crosscheck(conn)
        structure_summaries = summarize_structure_crosschecks(structure_crosscheck)
        latest_cross_history = latest_structure_crosscheck_history(conn)
        for summary in structure_summaries:
            hist = latest_cross_history.get(summary["structure_id"])
            summary["last_crosscheck_at"] = hist["created_at"] if hist else None
            latest_monitor = _parse_dt_br(summary.get("latest_monitor_at"))
            last_cross = _parse_dt_br(summary.get("last_crosscheck_at"))
            summary["crosscheck_stale"] = bool(latest_monitor and (not last_cross or latest_monitor > last_cross))
        summary_map = {r["process_key"]: dict(r) for r in summary_rows}
        machining_summary = summary_map.get("usinagem", {"total":0,"ok":0,"warning":0,"bad":0,"analyzed_at":None})
        laser_summary = summary_map.get("corte_laser", {"total":0,"ok":0,"warning":0,"bad":0,"analyzed_at":None})
        library_summary = summary_map.get("biblioteca_cad", {"total":0,"ok":0,"warning":0,"bad":0,"analyzed_at":None})
        machining_snapshot = get_process_scan_snapshot("usinagem")
        laser_snapshot = get_process_scan_snapshot("corte_laser")
        library_snapshot = get_process_scan_snapshot("biblioteca_cad")
        laser_path = ""
        library_path = ""
        for env in process_envs:
            if env["process_key"] == "corte_laser":
                laser_path = env["official_folder_path"] or ""
            elif env["process_key"] == "biblioteca_cad":
                library_path = env["official_folder_path"] or ""
        history = conn.execute("""
            SELECT v.*, u.name AS validator_name
            FROM validation_events v
            LEFT JOIN users u ON u.id=v.user_id
            ORDER BY v.id DESC LIMIT 50
        """).fetchall()
        involved = conn.execute(
            "SELECT id,name,email,company,created_at FROM users ORDER BY name"
        ).fetchall()
        logs = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT 50"
        ).fetchall()
        evidence = conn.execute(
            "SELECT * FROM evidence_events ORDER BY id DESC LIMIT 100"
        ).fetchall()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "settings": settings,
        "process_envs": process_envs,
        "laser_path": laser_path,
        "machining_summary": machining_summary,
        "laser_summary": laser_summary,
        "library_summary": library_summary,
        "machining_snapshot": machining_snapshot,
        "laser_snapshot": laser_snapshot,
        "library_snapshot": library_snapshot,
        "library_path": library_path,
        "product_structures": product_structures,
        "product_structure_items": product_structure_items,
        "structure_crosscheck": structure_crosscheck,
        "structure_summaries": structure_summaries,
        "history": history,
        "involved": involved,
        "logs": logs,
        "evidence": evidence,
        "user_name": request.session.get("user_name", "Usuário")
    })

@router.post("/corporate-folder")
def set_corporate_folder(request: Request,
                         environment_name: str = Form("Usinagem Interna"),
                         path: str = Form(...)):
    # Compatibilidade com versões anteriores: trata como processo de usinagem.
    return set_process_environment(request, "usinagem", path)

@router.post("/process-environment")
def set_process_environment(request: Request,
                            process_key: str = Form(...),
                            path: str = Form(...)):
    uid = require_user(request)
    if not uid:
        return RedirectResponse("/", status_code=303)

    process_key = process_key.strip()
    path = path.strip().strip('"')

    if not Path(path).is_dir():
        target_view = "monitor" if process_key == "usinagem" else "laser"
        return RedirectResponse(
            f"/dashboard?view={target_view}&error=pasta_invalida&process={process_key}",
            status_code=303
        )

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    with get_conn() as conn:
        if process_key == "usinagem":
            conn.execute("""
                UPDATE corporate_settings
                SET environment_name='Usinagem Interna',
                    official_folder_path=?,
                    updated_by=?,
                    updated_at=?
                WHERE id=1
            """, (path, uid, now))
            conn.execute("""
                INSERT INTO process_environments
                (process_key,process_name,official_folder_path,active,updated_by,updated_at)
                VALUES('usinagem','Usinagem Interna',?,1,?,?)
                ON CONFLICT(process_key) DO UPDATE SET
                    official_folder_path=excluded.official_folder_path,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
            """, (path, uid, now))
            target_view = "monitor"
        elif process_key == "corte_laser":
            conn.execute("""
                INSERT INTO process_environments
                (process_key,process_name,official_folder_path,active,updated_by,updated_at)
                VALUES('corte_laser','Corte a Laser',?,1,?,?)
                ON CONFLICT(process_key) DO UPDATE SET
                    official_folder_path=excluded.official_folder_path,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
            """, (path, uid, now))
            target_view = "laser"
        elif process_key == "biblioteca_cad":
            conn.execute("""
                INSERT INTO process_environments
                (process_key,process_name,official_folder_path,active,updated_by,updated_at)
                VALUES('biblioteca_cad','Biblioteca CAD',?,1,?,?)
                ON CONFLICT(process_key) DO UPDATE SET
                    official_folder_path=excluded.official_folder_path, updated_by=excluded.updated_by, updated_at=excluded.updated_at
            """, (path, uid, now))
            target_view = "library"
        else:
            return RedirectResponse("/dashboard?error=processo_invalido", status_code=303)

    audit(request, "PASTA_PROCESSO_ATUALIZADA", f"{process_key} | {path}")
    return RedirectResponse(
        f"/dashboard?view={target_view}&saved=1&process={process_key}",
        status_code=303
    )



@router.post("/product-structure/analyze")
async def analyze_product_structure(
    request: Request,
    file: UploadFile = File(...),
    supplemental_text: str = Form("")
):
    uid = require_user(request)
    if not uid:
        return RedirectResponse("/", status_code=303)

    content = await file.read()
    try:
        extracted, source_type = extract_text(file.filename, content)
    except ValueError:
        return RedirectResponse("/dashboard?view=structure&structure_error=formato", status_code=303)

    combined = "\n".join(x for x in [extracted, supplemental_text.strip()] if x)
    items = parse_structure_text(combined)

    # Fingerprint baseado no conteúdo efetivamente analisado.
    source_hash = hashlib.sha256(
        (file.filename + "\n" + combined).encode("utf-8", errors="ignore")
    ).hexdigest()

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    user_name = request.session.get("user_name", "Usuário")

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM product_structures WHERE source_hash=? ORDER BY id DESC LIMIT 1",
            (source_hash,)
        ).fetchone()

        if existing:
            sid = existing["id"]
            # Reanálise do mesmo conteúdo substitui os itens daquela estrutura.
            conn.execute("DELETE FROM product_structure_items WHERE structure_id=?", (sid,))
            conn.execute("""
                UPDATE product_structures
                SET source_name=?, source_type=?, extracted_text=?, created_at=?,
                    created_by=?, created_by_name=?
                WHERE id=?
            """, (file.filename, source_type, combined, now, uid, user_name, sid))
            duplicate_replaced = True
        else:
            cur = conn.execute("""
                INSERT INTO product_structures
                (source_name,source_type,extracted_text,source_hash,created_at,created_by,created_by_name)
                VALUES(?,?,?,?,?,?,?)
            """, (file.filename, source_type, combined, source_hash, now, uid, user_name))
            sid = cur.lastrowid
            duplicate_replaced = False

        for item in items:
            conn.execute("""
                INSERT INTO product_structure_items
                (structure_id,code,prefix,origin_type,internal_external,family,description,evaluation_scope)
                VALUES(?,?,?,?,?,?,?,?)
            """, (
                sid, item["code"], item["prefix"], item["origin_type"],
                item["internal_external"], item["family"], item["description"],
                item["evaluation_scope"]
            ))

    event = "ESTRUTURA_PRODUTO_REANALISADA" if duplicate_replaced else "ESTRUTURA_PRODUTO_ANALISADA"
    audit(request, event, f"{file.filename} | {len(items)} códigos")

    flag = "replaced=1" if duplicate_replaced else "structure_saved=1"
    return RedirectResponse(
        f"/dashboard?view=structure&structure_id={sid}&{flag}",
        status_code=303
    )


@router.post("/product-structure/{structure_id}/delete")
def delete_product_structure(request: Request, structure_id: int):
    uid = require_user(request)
    if not uid:
        return RedirectResponse("/", status_code=303)

    with get_conn() as conn:
        row = conn.execute(
            "SELECT source_name FROM product_structures WHERE id=?",
            (structure_id,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM product_structure_items WHERE structure_id=?", (structure_id,))
            conn.execute("DELETE FROM product_structures WHERE id=?", (structure_id,))
            source_name = row["source_name"]
        else:
            source_name = f"ID {structure_id}"

    audit(request, "ESTRUTURA_PRODUTO_EXCLUIDA", source_name)
    return RedirectResponse("/dashboard?view=structure&deleted=1", status_code=303)


@router.post("/product-structure/clear-all")
def clear_all_product_structures(request: Request):
    uid = require_user(request)
    if not uid:
        return RedirectResponse("/", status_code=303)

    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM product_structures").fetchone()["n"]
        conn.execute("DELETE FROM product_structure_items")
        conn.execute("DELETE FROM product_structures")

    audit(request, "ESTRUTURAS_PRODUTO_LIMPAS", f"{count} estrutura(s) removida(s)")
    return RedirectResponse("/dashboard?view=structure&cleared=1", status_code=303)


@router.post("/api/structure-crosscheck/save")
def save_structure_crosscheck(request: Request):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    with get_conn() as conn:
        rows = get_structure_crosscheck(conn)
        summaries = summarize_structure_crosschecks(rows)
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        user_name = request.session.get("user_name", "Usuário")

        for summary in summaries:
            conn.execute("""
                INSERT INTO structure_crosscheck_history
                (structure_id,source_name,total_codes,internal_codes,compliant_codes,
                 incomplete_codes,missing_codes,external_codes,prepared_codes,
                 overall_status,snapshot_json,created_at,created_by,created_by_name)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                summary["structure_id"], summary["source_name"], summary["total_codes"],
                summary["internal_codes"], summary["compliant_codes"],
                summary["incomplete_codes"], summary["missing_codes"],
                summary["external_codes"], summary["prepared_codes"],
                summary["overall_status"],
                json.dumps(summary["items"], ensure_ascii=False, default=str),
                now, uid, user_name
            ))

    audit(request, "CRUZAMENTO_ESTRUTURA_ATUALIZADO", f"{len(summaries)} estrutura(s)")
    return {"ok": True, "updated_at": now, "structures": summaries}

@router.get("/api/structure-crosscheck")
def structure_crosscheck_api(request: Request):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    with get_conn() as conn:
        rows = get_structure_crosscheck(conn)
    return {"results": rows}



@router.post("/api/save-snapshot/{process_key}")
async def save_snapshot_api(request: Request, process_key: str):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    if process_key not in ("usinagem", "corte_laser"):
        return JSONResponse({"error": "Processo inválido"}, status_code=400)

    payload = await request.json()
    results = payload.get("results") or []
    environment_name = payload.get("environment_name") or (
        "Usinagem Interna" if process_key == "usinagem" else "Corte a Laser"
    )
    folder_path = payload.get("folder_path") or ""

    save_process_scan_snapshot(
        process_key, environment_name, folder_path, results, uid,
        request.session.get("user_name", "Usuário")
    )
    return {"ok": True, "count": len(results)}


@router.get("/api/snapshot-status")
def snapshot_status(request: Request):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    machining = get_process_scan_snapshot("usinagem")
    laser = get_process_scan_snapshot("corte_laser")
    return {
        "usinagem": {
            "exists": bool(machining),
            "count": len((machining or {}).get("results") or []),
            "analyzed_at": (machining or {}).get("analyzed_at")
        },
        "corte_laser": {
            "exists": bool(laser),
            "count": len((laser or {}).get("results") or []),
            "analyzed_at": (laser or {}).get("analyzed_at")
        }
    }

@router.get("/api/last-scan/{process_key}")
def last_scan(request: Request, process_key: str):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    if process_key not in ("usinagem", "corte_laser"):
        return JSONResponse({"error": "Processo inválido"}, status_code=400)

    snapshot = get_process_scan_snapshot(process_key)
    if not snapshot:
        return {
            "process_key": process_key,
            "has_snapshot": False,
            "results": []
        }

    snapshot["has_snapshot"] = True
    return snapshot

@router.get("/api/process-summaries")
def process_summaries(request: Request):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    defaults = {"total": 0, "ok": 0, "warning": 0, "bad": 0, "analyzed_at": None}
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM process_scan_summary").fetchall()

    result = {
        "usinagem": dict(defaults),
        "corte_laser": dict(defaults),
    }
    for row in rows:
        key = row["process_key"]
        if key in result:
            result[key] = {
                "total": row["total"],
                "ok": row["ok"],
                "warning": row["warning"],
                "bad": row["bad"],
                "analyzed_at": row["analyzed_at"],
            }
    return result

@router.get("/api/scan-library")
def scan_library(request: Request):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error":"Não autenticado"}, status_code=401)
    with get_conn() as conn:
        env=conn.execute("SELECT * FROM process_environments WHERE process_key='biblioteca_cad'").fetchone()
    if not env or not env["official_folder_path"]:
        return JSONResponse({"error":"A pasta oficial da Biblioteca CAD ainda não foi configurada."}, status_code=400)
    try:
        results=scan_library_root(env["official_folder_path"])
    except Exception as e:
        return JSONResponse({"error":str(e)}, status_code=400)
    summary=save_process_summary("biblioteca_cad", results, uid, request.session.get("user_name","Usuário"))
    save_process_scan_snapshot("biblioteca_cad", env["process_name"], env["official_folder_path"], results, uid, request.session.get("user_name","Usuário"))
    audit(request,"ANALISE_BIBLIOTECA_CAD",f"{len(results)} pastas de itens analisadas")
    return {"environment_name":env["process_name"],"folder_path":env["official_folder_path"],"results":results,"summary":summary}

@router.get("/api/scan-laser")
def scan_laser(request: Request):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    with get_conn() as conn:
        env = conn.execute(
            "SELECT * FROM process_environments WHERE process_key='corte_laser'"
        ).fetchone()

    if not env or not env["official_folder_path"]:
        return JSONResponse(
            {"error": "A pasta oficial de Corte a Laser ainda não foi configurada."},
            status_code=400
        )

    try:
        results = scan_laser_root(env["official_folder_path"])
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    sync_file_evidence(
        results,
        user_id=uid,
        user_name=request.session.get("user_name", "Usuário")
    )
    laser_summary = save_process_summary(
        "corte_laser", results, uid, request.session.get("user_name", "Usuário")
    )
    save_monitored_code_results("corte_laser", results)
    save_process_scan_snapshot(
        "corte_laser",
        env["process_name"],
        env["official_folder_path"],
        results,
        uid,
        request.session.get("user_name", "Usuário")
    )
    audit(request, "ANALISE_CORTE_LASER", f"{len(results)} pastas analisadas")
    return {
        "environment_name": env["process_name"],
        "folder_path": env["official_folder_path"],
        "results": results,
        "summary": laser_summary
    }

@router.get("/api/scan")
def scan(request: Request):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    with get_conn() as conn:
        settings = conn.execute("SELECT * FROM corporate_settings WHERE id=1").fetchone()

    if not settings or not settings["official_folder_path"]:
        return JSONResponse({"error": "A pasta oficial ainda não foi configurada."}, status_code=400)

    try:
        results = scan_root(settings["official_folder_path"])
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    with get_conn() as conn:
        for r in results:
            verified = conn.execute(
                "SELECT v.*, u.name AS validator_name FROM validation_events v "
                "LEFT JOIN users u ON u.id=v.user_id "
                "WHERE v.folder_path=? AND v.issue_signature=? "
                "ORDER BY v.id DESC LIMIT 1",
                (r["folder_path"], r["signature"])
            ).fetchone()
            r["verified"] = bool(verified)
            r["verified_by"] = verified["validator_name"] if verified else None
            r["verified_note"] = verified["note"] if verified else None
            r["verified_at"] = verified["validated_at"] if verified else None
            if r["verified"] and r["problems"]:
                r["status"] = "verificado"

    sync_file_evidence(
        results,
        user_id=uid,
        user_name=request.session.get("user_name", "Usuário")
    )
    machining_summary = save_process_summary(
        "usinagem", results, uid, request.session.get("user_name", "Usuário")
    )
    save_monitored_code_results("usinagem", results)
    save_process_scan_snapshot(
        "usinagem",
        settings["environment_name"],
        settings["official_folder_path"],
        results,
        uid,
        request.session.get("user_name", "Usuário")
    )
    audit(request, "ANALISE_EXECUTADA", f"{len(results)} pastas analisadas")
    return {
        "environment_name": settings["environment_name"],
        "folder_path": settings["official_folder_path"],
        "results": results,
        "summary": machining_summary
    }


def _configured_roots():
    roots=[]
    with get_conn() as conn:
        s=conn.execute("SELECT official_folder_path FROM corporate_settings WHERE id=1").fetchone()
        if s and s["official_folder_path"]:
            roots.append(Path(s["official_folder_path"]).expanduser().resolve())
        for row in conn.execute("SELECT official_folder_path FROM process_environments WHERE official_folder_path IS NOT NULL").fetchall():
            if row["official_folder_path"]:
                roots.append(Path(row["official_folder_path"]).expanduser().resolve())
    return roots

def _path_inside_configured_root(path: Path):
    try: resolved=path.expanduser().resolve()
    except Exception: return False
    for root in _configured_roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            pass
    return False

@router.post("/api/approved-rename")
def approved_rename(request: Request,
                    source_path: str = Form(...),
                    expected_name: str = Form(...),
                    kind: str = Form(...)):
    uid=require_user(request)
    if not uid:
        return JSONResponse({"error":"Não autenticado"},status_code=401)
    source=Path(source_path)
    if kind not in ("folder","file"):
        return JSONResponse({"error":"Tipo de correção inválido."},status_code=400)
    if not source.exists():
        return JSONResponse({"error":"O item original não existe mais. Execute uma nova análise."},status_code=409)
    if not _path_inside_configured_root(source):
        return JSONResponse({"error":"Alteração bloqueada: caminho fora das pastas monitoradas."},status_code=403)

    safe_name=Path(expected_name).name
    if safe_name != expected_name or safe_name in ("",".",".."):
        return JSONResponse({"error":"Nome de destino inválido."},status_code=400)
    target=source.with_name(safe_name)
    if target.exists():
        return JSONResponse({"error":f"Correção bloqueada: já existe '{safe_name}' no destino."},status_code=409)

    old_name=source.name
    try:
        source.rename(target)
    except PermissionError:
        return JSONResponse({"error":"Sem permissão para renomear ou o arquivo está em uso."},status_code=403)
    except OSError as e:
        return JSONResponse({"error":f"Não foi possível renomear: {e}"},status_code=400)

    audit(request,"CORRECAO_NOME_APROVADA_EXECUTADA",
          f"{kind} | {old_name} -> {safe_name} | {source} -> {target}")
    return {"ok":True,"old_name":old_name,"new_name":safe_name,
            "new_path":str(target),"message":f"Correção executada: {old_name} → {safe_name}"}

@router.post("/api/verify")
def verify(request: Request,
           folder_path: str = Form(...),
           signature: str = Form(...),
           note: str = Form(...)):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO validation_events
               (user_id,folder_path,issue_signature,decision,note,validated_at,app_version)
               VALUES(?,?,?,?,?,?,?)""",
            (uid, folder_path, signature, "VALIDADO_SEM_IMPACTO",
             note.strip(), now, "V0.6.2")
        )

    audit(request, "VALIDACAO_MANUAL", f"{folder_path} | {note.strip()}")
    return {
        "ok": True,
        "validator_name": request.session.get("user_name", "Usuário"),
        "validated_at": now
    }

@router.post("/api/open-folder")
def open_folder(request: Request, path: str = Form(...)):
    uid = require_user(request)
    if not uid:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    if os.name != "nt":
        return JSONResponse({"error": "Abertura automática disponível apenas no Windows."}, status_code=400)
    try:
        os.startfile(path)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
