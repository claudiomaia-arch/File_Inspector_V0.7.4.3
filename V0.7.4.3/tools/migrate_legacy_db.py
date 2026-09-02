import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
import sys
import os

DATA_ROOT = Path(os.getenv("CAD_INSPECTOR_DATA_DIR", str(Path.home() / "CAD_Usinagem_Inspector_DATA"))).expanduser()
TARGET = DATA_ROOT / "inspector.db"
BACKUPS = DATA_ROOT / "backups"

def find_db(input_path: Path):
    input_path = input_path.expanduser().resolve()
    if input_path.is_file() and input_path.name.lower().endswith(".db"):
        return input_path
    candidates = [
        input_path / "data" / "inspector.db",
        input_path / "inspector.db",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

def main():
    print("=" * 60)
    print("CAD INSPECTOR V0.5 - MIGRAÇÃO DE DADOS LEGADOS")
    print("=" * 60)
    print()
    raw = input("Cole o caminho da pasta da versão anterior (ex.: V0.4.3): ").strip().strip('"')
    source = find_db(Path(raw))
    if not source:
        print("\nBanco inspector.db não encontrado no caminho informado.")
        input("Pressione ENTER para sair...")
        return 1

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    if TARGET.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUPS / f"inspector_antes_importacao_{stamp}.db"
        shutil.copy2(TARGET, backup)
        print(f"\nBackup do banco persistente criado em:\n{backup}")
        answer = input("\nJá existe um banco persistente. Substituir pelo banco legado? (S/N): ").strip().upper()
        if answer != "S":
            print("Importação cancelada. Nenhum dado foi substituído.")
            input("Pressione ENTER para sair...")
            return 0

    shutil.copy2(source, TARGET)
    print(f"\nBanco importado com sucesso:\n{source}\n→\n{TARGET}")
    print("\nAo iniciar a V0.5, a migração de schema será executada automaticamente.")
    input("Pressione ENTER para concluir...")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
