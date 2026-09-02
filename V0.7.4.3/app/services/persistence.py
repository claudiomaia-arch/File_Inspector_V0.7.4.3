from datetime import datetime
from app.database import get_conn

APP_VERSION = "V0.5.0"

def sync_file_evidence(results, user_id=None, user_name=None):
    """
    Atualiza o estado corrente dos arquivos e cria eventos imutáveis quando
    um arquivo aparece, muda de conteúdo ou deixa de existir.
    """
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    current = {}

    for result in results:
        for item in result.get("file_inventory", []):
            current[item["file_path"]] = item

    with get_conn() as conn:
        previous_rows = conn.execute("SELECT * FROM file_state").fetchall()
        previous = {r["file_path"]: dict(r) for r in previous_rows}

        # Novos / alterados
        for path, item in current.items():
            old = previous.get(path)
            if old is None:
                conn.execute(
                    """INSERT INTO evidence_events
                       (event_type,folder_path,file_path,file_kind,
                        previous_hash,current_hash,previous_size,current_size,
                        detected_at,detected_by_user_id,detected_by_user_name,
                        app_version,details)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("ARQUIVO_ADICIONADO", item["folder_path"], path, item["file_kind"],
                     None, item["sha256"], None, item["size"], now,
                     user_id, user_name, APP_VERSION,
                     "Arquivo identificado pela primeira vez no monitoramento.")
                )
            elif old["sha256"] != item["sha256"]:
                conn.execute(
                    """INSERT INTO evidence_events
                       (event_type,folder_path,file_path,file_kind,
                        previous_hash,current_hash,previous_size,current_size,
                        detected_at,detected_by_user_id,detected_by_user_name,
                        app_version,details)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("ARQUIVO_ALTERADO", item["folder_path"], path, item["file_kind"],
                     old["sha256"], item["sha256"], old["size"], item["size"], now,
                     user_id, user_name, APP_VERSION,
                     "Conteúdo do arquivo alterado (SHA-256 diferente).")
                )

            conn.execute(
                """INSERT INTO file_state
                   (file_path,folder_path,file_kind,size,mtime_ns,sha256,last_seen_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(file_path) DO UPDATE SET
                     folder_path=excluded.folder_path,
                     file_kind=excluded.file_kind,
                     size=excluded.size,
                     mtime_ns=excluded.mtime_ns,
                     sha256=excluded.sha256,
                     last_seen_at=excluded.last_seen_at""",
                (path, item["folder_path"], item["file_kind"], item["size"],
                 item["mtime_ns"], item["sha256"], now)
            )

        # Removidos
        for path, old in previous.items():
            if path not in current:
                conn.execute(
                    """INSERT INTO evidence_events
                       (event_type,folder_path,file_path,file_kind,
                        previous_hash,current_hash,previous_size,current_size,
                        detected_at,detected_by_user_id,detected_by_user_name,
                        app_version,details)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("ARQUIVO_REMOVIDO", old["folder_path"], path, old["file_kind"],
                     old["sha256"], None, old["size"], None, now,
                     user_id, user_name, APP_VERSION,
                     "Arquivo deixou de ser encontrado na pasta monitorada.")
                )
                conn.execute("DELETE FROM file_state WHERE file_path=?", (path,))
