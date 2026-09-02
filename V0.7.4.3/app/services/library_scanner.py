from pathlib import Path
import re, hashlib

# V0.7.4.0 — regras iniciais da Biblioteca CAD.
# STEP/STP são deliberadamente ignorados nesta fase.
CODE_RE = re.compile(r"^([A-Z]{3}\d{6})\s+-\s+(.+)$", re.I)
EDITABLE_3D = {'.sldprt', '.ipt', '.prt', '.par'}
EDITABLE_2D = {'.slddrw', '.dwg'}
PDF_EXT = {'.pdf'}
IGNORED = {'.step', '.stp'}

def _signature(folder, problems):
    raw = str(folder) + '|' + '|'.join(problems)
    return hashlib.sha256(raw.encode('utf-8', errors='ignore')).hexdigest()

def scan_library_root(root_path: str):
    root = Path(root_path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('A pasta da Biblioteca CAD não existe ou não está acessível.')

    results=[]
    code_locations={}
    # Estrutura esperada: Biblioteca / Tipo do item / Código - Nome / arquivos
    for type_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p:p.name.lower()):
        for item_dir in sorted([p for p in type_dir.iterdir() if p.is_dir()], key=lambda p:p.name.lower()):
            m=CODE_RE.match(item_dir.name.strip())
            code=m.group(1).upper() if m else ''
            piece_name=m.group(2).strip() if m else ''
            files=[p for p in item_dir.iterdir() if p.is_file()]
            f3d=[p.name for p in files if p.suffix.lower() in EDITABLE_3D]
            f2d=[p.name for p in files if p.suffix.lower() in EDITABLE_2D]
            pdf=[p.name for p in files if p.suffix.lower() in PDF_EXT]
            ignored=[p.name for p in files if p.suffix.lower() in IGNORED]
            problems=[]; actions=[]
            if not m:
                problems.append("Pasta fora do padrão 'Código - Nome'.")
                actions.append("Adequar a pasta ao padrão Código - Nome da peça.")
            if not f3d:
                problems.append('Peça 3D editável não encontrada.')
                actions.append('Adicionar o arquivo 3D editável da peça.')
            if not f2d:
                problems.append('2D editável não encontrado.')
                actions.append('Adicionar o arquivo 2D editável da peça.')
            if not pdf:
                problems.append('PDF não encontrado.')
                actions.append('Adicionar o PDF da peça.')
            result={
                'type_name':type_dir.name, 'folder_name':item_dir.name, 'folder_path':str(item_dir),
                'code':code, 'piece_name':piece_name, 'folder_pattern_ok':bool(m),
                'part3d':bool(f3d), 'drawing2d':bool(f2d), 'pdf':bool(pdf),
                'part3d_files':f3d, 'drawing2d_files':f2d, 'pdf_files':pdf,
                'ignored_step_files':ignored, 'problems':problems, 'actions':actions,
                'status':'conforme' if not problems else 'incompleto'
            }
            result['signature']=_signature(item_dir, problems)
            results.append(result)
            if code: code_locations.setdefault(code, []).append(result)

    # Código repetido em mais de uma pasta é pendência e nunca é resolvido automaticamente.
    for code, rows in code_locations.items():
        if len(rows)>1:
            for r in rows:
                r['problems'].append(f'Duplicidade: o código {code} foi encontrado em {len(rows)} pastas da Biblioteca.')
                r['actions'].append('Revisar manualmente a duplicidade do código antes de considerar a documentação conforme.')
                r['status']='incompleto'
                r['signature']=_signature(Path(r['folder_path']), r['problems'])
    return results
