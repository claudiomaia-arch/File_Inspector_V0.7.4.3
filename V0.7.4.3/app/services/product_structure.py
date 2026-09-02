from __future__ import annotations
import io
import re
from pathlib import Path
from typing import List, Dict, Tuple

CODE_RE = re.compile(r"\b(USI|CRT|PRE)(0[13]\d{4})\b", re.IGNORECASE)

def extract_text(filename: str, content: bytes) -> Tuple[str, str]:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return text, "PDF"
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        # Image upload is accepted in V0.7. Automatic OCR is intentionally not
        # forced here because deployment machines may not have an OCR engine.
        # The UI allows the extracted/typed text to be supplied for analysis.
        return "", "IMAGEM"
    raise ValueError("Formato não suportado. Use PDF, PNG, JPG, JPEG, WEBP ou BMP.")

def classify_code(code: str) -> Dict[str, str]:
    code = code.upper()
    prefix = code[:3]
    origin = code[3:5]
    internal_external = "Interno" if origin == "03" else "Externo" if origin == "01" else "Não classificado"

    if prefix == "USI":
        family = "Usinados"
        scope = "Avaliar em Usinagem" if origin == "03" else "Fora da avaliação"
    elif prefix == "CRT":
        family = "Corte"
        scope = "Avaliar em Corte a Laser" if origin == "03" else "Fora da avaliação"
    else:
        family = "Preparados"
        scope = "Reconhecer / não avaliar"

    return {
        "code": code,
        "prefix": prefix,
        "origin_type": origin,
        "internal_external": internal_external,
        "family": family,
        "description": "",
        "evaluation_scope": scope,
    }

def parse_structure_text(text: str) -> List[Dict[str, str]]:
    seen = set()
    items = []
    for m in CODE_RE.finditer(text or ""):
        code = (m.group(1) + m.group(2)).upper()
        if code in seen:
            continue
        seen.add(code)
        items.append(classify_code(code))
    return items
