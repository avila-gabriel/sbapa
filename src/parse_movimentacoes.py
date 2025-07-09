"""
parse_movimentacoes.py - Biblioteca de extração de transações SBAPA

Fornece:
  • extract_movements_from_pdf(pdf_path: Path) -> List[Dict]
  • extract_all_movements(input_dir: Path) -> List[Dict]
  • write_movements_csv(rows: List[Dict], out_path: Path) -> None

Uso:
    from parse_movimentacoes import extract_all_movements, write_movements_csv
    rows = extract_all_movements(Path("input"))
    write_movements_csv(rows, Path("planilhas") / "movimentacoes.csv")
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple

import pdfplumber

# ── Expressões regulares ────────────────────────────────────────────────────
DATE_RE = re.compile(r"^(\d{2}/\d{2})")
VALOR_RE = re.compile(r"-?(?:\d{1,3}(?:\.\d{3})*|\d+)[.,]\d{2}-?(?!\.)")
PIX_CONTRA_RE = re.compile(r"PIX(?:ENVIADO|RECEBIDO)([A-Z][A-Za-zÁ-Úá-úÇç]+)")
LABEL_RE = re.compile(r"SaldodeContaCorrenteem(\d{2}/\d{2})")
NUM_RE = re.compile(r"[\d\.,]+")
RESUMO_RE = re.compile(r"Resumo\s*-\s*([a-zç]+/\d{4})", re.IGNORECASE)


def br_number_to_float(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def normalize_money(txt: str) -> float:
    neg = txt.endswith("-")
    val = br_number_to_float(txt.replace("-", ""))
    return -val if neg else val


def detect_via(text: str) -> str:
    t = text.lower()
    if "pixenviado" in t or "pixrecebido" in t:
        return "pix"
    if "debito" in t:
        return "debito"
    if "remuneracao" in t:
        return "rendimentos"
    if "tarifa" in t:
        return "tarifa"
    return "outro"


def detect_contraparte(text: str, via: str) -> str:
    if via != "pix":
        return ""
    m = PIX_CONTRA_RE.search(text)
    return m.group(1) if m else ""


def extract_saldos(pdf_path: Path) -> Tuple[str, float, str, float]:
    datas: List[str] = []
    saldos: List[float] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words() or []
            for i in range(len(words) - 1):
                label = words[i]["text"].replace(" ", "")
                m = LABEL_RE.fullmatch(label)
                if m:
                    date_str = m.group(1)
                    nxt = words[i + 1]["text"]
                    if NUM_RE.fullmatch(nxt):
                        datas.append(date_str)
                        saldos.append(br_number_to_float(nxt))
                if len(saldos) >= 2:
                    break
            if len(saldos) >= 2:
                break
    if len(saldos) < 2:
        raise ValueError("Não foi possível ler dois saldos no resumo.")
    return datas[0], saldos[0], datas[1], saldos[1]


def parse_mov(lines: List[str]) -> List[Dict]:
    rows: List[Dict] = []
    current_date = ""
    skip_next = False
    for raw in lines:
        if skip_next:
            skip_next = False
            continue
        r = raw.strip()
        if not r:
            continue
        mdate = DATE_RE.match(r)
        if mdate:
            current_date = mdate.group(1)
            content = r[mdate.end() :].strip()
        else:
            content = r
        if not current_date:
            continue
        mval = VALOR_RE.search(content)
        if not mval:
            continue
        val_str = mval.group(0)
        val = normalize_money(val_str)
        via = detect_via(content)
        tipo = "recebido" if val > 0 else "enviado"
        cp = detect_contraparte(content, via)
        rows.append(
            {
                "data": current_date,
                "valor": f"{val:.2f}",
                "via": via,
                "tipo": tipo,
                "contraparte": cp,
                "descricao_raw": r,
            }
        )
        if "TRANSFERENCIAPROGRAMADA" in r or "TRANSFPROGDIFERENTETITULARIDADE" in r:
            skip_next = True
    return rows


def extract_transacoes(pdf_path: Path) -> List[Dict]:
    cap = False
    lines: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for ln in (page.extract_text() or "").splitlines():
                strip = ln.strip()
                if not cap:
                    if "Movimentação" in strip:
                        cap = True
                    continue
                if strip.replace(" ", "").lower().startswith("sevocênãotem"):
                    cap = False
                    break
                if strip.startswith("SALDOEM") or strip.startswith("SALDO EM"):
                    continue
                lines.append(ln)
    return parse_mov(lines)


def extract_periodo(pdf_path: Path) -> str:
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            m = RESUMO_RE.search(text)
            if m:
                return m.group(1).strip().lower()
    raise ValueError("Período (Resumo - mês/ano) não encontrado.")


def extract_movements_from_pdf(
    pdf_path: Path, diff_threshold: float = 0.05
) -> List[Dict]:
    """
    Extrai todas as transações de um único PDF:
      - periódo e arquivo detectados automaticamente
      - verifica diferença de saldo e emite warning, mas não interrompe
    """
    periodo = extract_periodo(pdf_path)
    data_ini, saldo_ini, data_fim, saldo_fim = extract_saldos(pdf_path)
    trans = extract_transacoes(pdf_path)
    soma = sum(float(t["valor"]) for t in trans)
    diff = abs((saldo_ini + soma) - saldo_fim)
    if diff > diff_threshold:
        print(f"⚠️  {pdf_path.name}: diferença {diff:.2f} acima de {diff_threshold}")
    for t in trans:
        t["periodo"] = periodo
        t["arquivo"] = pdf_path.name
    return trans


def extract_all_movements(input_dir: Path) -> List[Dict]:
    """
    Extrai transações de todos os PDFs em 'input_dir'.
    Retorna lista concatenada de dicionários.
    """
    all_rows: List[Dict] = []
    pdfs = sorted(input_dir.glob("*.pdf"))
    for pdf in pdfs:
        print(f"→ {pdf.name}")
        try:
            rows = extract_movements_from_pdf(pdf)
            all_rows.extend(rows)
            print(f"  {len(rows)} transações extraídas.")
        except Exception as e:
            print(f"  ⚠️  Ignorado {pdf.name}: {e}")
    return all_rows


def write_movements_csv(rows: List[Dict], out_path: Path) -> None:
    """
    Escreve a lista de transações em CSV com cabeçalho padronizado.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "data",
                "valor",
                "via",
                "tipo",
                "contraparte",
                "descricao_raw",
                "periodo",
                "arquivo",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"✔️  CSV final gravado: {out_path} ({len(rows)} linhas)")


def main() -> None:
    rows = extract_all_movements(Path("input"))
    if not rows:
        print("Nenhuma transação válida encontrada.")
        return
    write_movements_csv(rows, Path("planilhas") / "movimentacoes.csv")


if __name__ == "__main__":
    main()
