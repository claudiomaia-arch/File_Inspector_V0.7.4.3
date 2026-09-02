import os
import shutil
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

APP_DIR = Path(__file__).resolve().parent.parent

# A partir da V0.5, os dados NÃO ficam dentro da pasta da versão.
# Assim V0.5, V0.6, V0.7... utilizam o mesmo banco corporativo.
DEFAULT_DATA_ROOT = Path.home() / "CAD_Usinagem_Inspector_DATA"
DATA_ROOT = Path(os.getenv("CAD_INSPECTOR_DATA_DIR", str(DEFAULT_DATA_ROOT))).expanduser().resolve()
DB_PATH = DATA_ROOT / "inspector.db"
BACKUP_DIR = DATA_ROOT / "backups"
LOG_DIR = DATA_ROOT / "logs"

SCHEMA_VERSION = 5

def ensure_data_dirs():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

@contextmanager
def get_conn():
    ensure_data_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone() is not None

def _column_exists(conn, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return any(r["name"] == column for r in conn.execute(f"PRAGMA table_info({table})"))

def current_schema_version(conn) -> int:
    if not _table_exists(conn, "schema_meta"):
        return 0
    row = conn.execute("SELECT schema_version FROM schema_meta WHERE id=1").fetchone()
    return int(row["schema_version"]) if row else 0

def backup_database(reason: str = "migration") -> Path | None:
    ensure_data_dirs()
    if not DB_PATH.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)
    dest = BACKUP_DIR / f"inspector_{stamp}_{safe_reason}.db"
    shutil.copy2(DB_PATH, dest)
    return dest

def _create_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS schema_meta (
        id INTEGER PRIMARY KEY CHECK (id=1),
        schema_version INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        company TEXT,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS corporate_settings (
        id INTEGER PRIMARY KEY CHECK (id=1),
        environment_name TEXT NOT NULL DEFAULT 'Usinagem Interna',
        official_folder_path TEXT,
        updated_by INTEGER,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS process_environments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        process_key TEXT NOT NULL UNIQUE,
        process_name TEXT NOT NULL,
        official_folder_path TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        updated_by INTEGER,
        updated_at TEXT
    );


    CREATE TABLE IF NOT EXISTS product_structures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_name TEXT NOT NULL,
        source_type TEXT NOT NULL,
        extracted_text TEXT,
        source_hash TEXT,
        created_at TEXT NOT NULL,
        created_by INTEGER,
        created_by_name TEXT
    );

    CREATE TABLE IF NOT EXISTS product_structure_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        structure_id INTEGER NOT NULL,
        code TEXT NOT NULL,
        prefix TEXT NOT NULL,
        origin_type TEXT NOT NULL,
        internal_external TEXT NOT NULL,
        family TEXT,
        description TEXT,
        evaluation_scope TEXT NOT NULL,
        FOREIGN KEY(structure_id) REFERENCES product_structures(id)
    );

    CREATE TABLE IF NOT EXISTS structure_crosscheck_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        structure_id INTEGER,
        source_name TEXT NOT NULL,
        total_codes INTEGER NOT NULL DEFAULT 0,
        internal_codes INTEGER NOT NULL DEFAULT 0,
        compliant_codes INTEGER NOT NULL DEFAULT 0,
        incomplete_codes INTEGER NOT NULL DEFAULT 0,
        missing_codes INTEGER NOT NULL DEFAULT 0,
        external_codes INTEGER NOT NULL DEFAULT 0,
        prepared_codes INTEGER NOT NULL DEFAULT 0,
        overall_status TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by INTEGER,
        created_by_name TEXT
    );


    CREATE TABLE IF NOT EXISTS process_scan_summary (
        process_key TEXT PRIMARY KEY,
        total INTEGER NOT NULL DEFAULT 0,
        ok INTEGER NOT NULL DEFAULT 0,
        warning INTEGER NOT NULL DEFAULT 0,
        bad INTEGER NOT NULL DEFAULT 0,
        analyzed_at TEXT,
        analyzed_by INTEGER,
        analyzed_by_name TEXT
    );

    CREATE TABLE IF NOT EXISTS process_scan_snapshot (
        process_key TEXT PRIMARY KEY,
        environment_name TEXT,
        folder_path TEXT,
        results_json TEXT NOT NULL,
        analyzed_at TEXT NOT NULL,
        analyzed_by INTEGER,
        analyzed_by_name TEXT
    );


    CREATE TABLE IF NOT EXISTS monitored_code_results (
        process_key TEXT NOT NULL,
        code TEXT NOT NULL,
        folder_name TEXT NOT NULL,
        folder_path TEXT NOT NULL,
        status TEXT NOT NULL,
        problems_json TEXT,
        actions_json TEXT,
        signature TEXT,
        analyzed_at TEXT,
        PRIMARY KEY(process_key, code)
    );

    CREATE INDEX IF NOT EXISTS idx_monitored_code_results_process
        ON monitored_code_results(process_key, status);

    CREATE TABLE IF NOT EXISTS validations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        folder_path TEXT NOT NULL,
        issue_signature TEXT NOT NULL,
        note TEXT,
        validated_at TEXT NOT NULL
    );

    -- V0.5: histórico imutável de validações. Nunca usa INSERT OR REPLACE.
    CREATE TABLE IF NOT EXISTS validation_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        folder_path TEXT NOT NULL,
        issue_signature TEXT NOT NULL,
        decision TEXT NOT NULL DEFAULT 'VALIDADO_SEM_IMPACTO',
        note TEXT NOT NULL,
        validated_at TEXT NOT NULL,
        app_version TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_validation_events_lookup
        ON validation_events(folder_path, issue_signature, id);

    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        user_name TEXT,
        action TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    );

    -- Evidências imutáveis de alteração detectadas nos arquivos monitorados.
    CREATE TABLE IF NOT EXISTS evidence_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        folder_path TEXT,
        file_path TEXT,
        file_kind TEXT,
        previous_hash TEXT,
        current_hash TEXT,
        previous_size INTEGER,
        current_size INTEGER,
        detected_at TEXT NOT NULL,
        detected_by_user_id INTEGER,
        detected_by_user_name TEXT,
        app_version TEXT NOT NULL,
        details TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_evidence_events_folder
        ON evidence_events(folder_path, id);

    -- Estado corrente é separado do histórico.
    CREATE TABLE IF NOT EXISTS file_state (
        file_path TEXT PRIMARY KEY,
        folder_path TEXT NOT NULL,
        file_kind TEXT,
        size INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        last_seen_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        used_at TEXT,
        created_at TEXT NOT NULL
    );

    INSERT OR IGNORE INTO corporate_settings(id, environment_name)
    VALUES(1, 'Usinagem Interna');

    INSERT OR IGNORE INTO process_environments(process_key,process_name,active)
    VALUES('usinagem','Usinagem Interna',1);

    INSERT OR IGNORE INTO process_environments(process_key,process_name,active)
    VALUES('corte_laser','Corte a Laser',1);

    INSERT OR IGNORE INTO process_environments(process_key,process_name,active)
    VALUES('biblioteca_cad','Biblioteca CAD',1);
    """)

def _migrate_legacy_validations(conn):
    """Copia validações antigas para o histórico novo sem apagar a tabela antiga."""
    if not _table_exists(conn, "validations"):
        return
    rows = conn.execute("SELECT * FROM validations ORDER BY id").fetchall()
    for r in rows:
        exists = conn.execute(
            """SELECT 1 FROM validation_events
               WHERE user_id=? AND folder_path=? AND issue_signature=?
                 AND note=? AND validated_at=?""",
            (r["user_id"], r["folder_path"], r["issue_signature"],
             r["note"] or "", r["validated_at"])
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO validation_events
                   (user_id,folder_path,issue_signature,decision,note,validated_at,app_version)
                   VALUES(?,?,?,?,?,?,?)""",
                (r["user_id"], r["folder_path"], r["issue_signature"],
                 "LEGADO_IMPORTADO", r["note"] or "",
                 r["validated_at"], "V0.4.x")
            )


def _ensure_v0711_columns(conn):
    """Garante colunas adicionadas após a criação inicial do banco persistente."""
    if _table_exists(conn, "product_structures"):
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(product_structures)").fetchall()
        }
        if "source_hash" not in cols:
            conn.execute("ALTER TABLE product_structures ADD COLUMN source_hash TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_product_structures_hash "
            "ON product_structures(source_hash)"
        )

def init_db():
    ensure_data_dirs()

    db_preexisted = DB_PATH.exists()
    old_version = 0

    if db_preexisted:
        with sqlite3.connect(DB_PATH) as raw:
            raw.row_factory = sqlite3.Row
            if raw.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
            ).fetchone():
                row = raw.execute("SELECT schema_version FROM schema_meta WHERE id=1").fetchone()
                old_version = int(row["schema_version"]) if row else 0

        if old_version < SCHEMA_VERSION:
            backup_database(f"antes_schema_{old_version}_para_{SCHEMA_VERSION}")

    with get_conn() as conn:
        _create_schema(conn)
        _ensure_v0711_columns(conn)
        _migrate_legacy_validations(conn)
        conn.execute(
            """INSERT INTO schema_meta(id,schema_version,updated_at)
               VALUES(1,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 schema_version=excluded.schema_version,
                 updated_at=excluded.updated_at""",
            (SCHEMA_VERSION, datetime.now().isoformat(timespec="seconds"))
        )

def get_data_info():
    return {
        "data_root": str(DATA_ROOT),
        "db_path": str(DB_PATH),
        "backup_dir": str(BACKUP_DIR),
        "schema_version": SCHEMA_VERSION,
    }
