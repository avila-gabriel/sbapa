"""
main.py - Orquestra todo o fluxo SBAPA com refatoração para biblioteca de extração:

1. Lê os períodos já processados em planilhas/movimentacoes.csv (se existir)
2. Para cada PDF bruto em ./extratos/:
   • Verifica que comece com “Fale Conosco”
   • Extrai o período (“janeiro/2025”) da linha “Resumo - mês/ano”
   • Se o período já estiver no CSV:
       - Remove o PDF de ./extratos/
       - Pula para o próximo
   • Caso contrário:
       - Pergunta interativamente faixa de páginas
       - Gera versão aparada em ./input/
3. Se não existir CSV ou houve novos trims ou o usuário solicitar:
   • Faz backup do CSV existente em ./last_planilhas/
   • Executa extração via extract_all_movements() e write_movements_csv()
4. Lê o CSV gerado e exibe:
   • Todos os períodos em ordem cronológica
   • Lacunas mensais entre eles
   • Quais arquivos referenciados não estão mais em ./input/
"""

import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber
from dateutil.relativedelta import relativedelta

from parse_movimentacoes import extract_all_movements, write_movements_csv
from trim import get_num_pages, trim_pdf

# ── Config ────────────────────────────────────────────────────────────────
EXTRATO_DIR = Path("extratos")
INPUT_DIR = Path("input")
CSV_PATH = Path("planilhas") / "movimentacoes.csv"
BACKUP_DIR = Path("last_planilhas")

KEY_PHRASE = "Fale Conosco"
RESUMO_RE = re.compile(r"Resumo\s*-\s*([A-Za-zçÇ]+/\d{4})", re.IGNORECASE)
MONTHS_PT = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
# ────────────────────────────────────────────────────────────────────────────


def extract_periodo(pdf_path: Path) -> str:
    """Extrai 'mes/ano' de 'Resumo - mês/ano' no PDF, após validar KEY_PHRASE."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        first = (pdf.pages[0].extract_text() or "").strip()
        if not first.startswith(KEY_PHRASE):
            raise ValueError("não começa com 'Fale Conosco'")
        for page in pdf.pages:
            txt = page.extract_text() or ""
            m = RESUMO_RE.search(txt)
            if m:
                return m.group(1).lower()
    raise ValueError("linha 'Resumo - mês/ano' não encontrada")


def periodo_to_date(periodo: str) -> datetime:
    """Converte 'mes/ano' em datetime no dia 1 para ordenação."""
    mes, ano = periodo.split("/")
    num = MONTHS_PT.get(mes)
    if not num:
        raise ValueError(f"Mês inválido: {mes}")
    return datetime(int(ano), num, 1)


def list_gaps(sorted_periodos: list[str]) -> list[str]:
    """Dada lista ordenada de 'mes/ano', devolve os meses faltantes."""
    if len(sorted_periodos) < 2:
        return []
    dates = [periodo_to_date(p) for p in sorted_periodos]
    gaps = []
    cur = dates[0] + relativedelta(months=1)
    i = 1
    while i < len(dates):
        if cur < dates[i]:
            gaps.append(cur.strftime("%m/%Y"))
            cur += relativedelta(months=1)
        else:
            cur = dates[i] + relativedelta(months=1)
            i += 1
    return gaps


def main() -> None:
    # 1) Preparar pastas
    if not EXTRATO_DIR.is_dir():
        sys.exit("❌ Pasta 'extratos/' não encontrada.")
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # 2) Carrega períodos já processados
    if CSV_PATH.is_file():
        df_exist = pd.read_csv(CSV_PATH, dtype=str, encoding="utf-8")
        processed = set(df_exist["periodo"].dropna().unique())
    else:
        processed = set()

    # 3) Itera sobre PDFs brutos
    pdfs = sorted(EXTRATO_DIR.glob("*.pdf"))
    if not pdfs:
        print("⚠️  Nenhum PDF em 'extratos/'.")
        return

    new_count = 0
    for pdf in pdfs:
        print(f"\n▶️  Processando '{pdf.name}'")
        try:
            periodo = extract_periodo(pdf)
        except ValueError as e:
            print(f"   ⚠️ Ignorado: {e}")
            continue

        if periodo in processed:
            print(f"   ⏭  Período {periodo} já processado; removendo PDF.")
            pdf.unlink()
            continue

        total = get_num_pages(pdf)
        print(f"   → Período: {periodo} | Páginas: 1-{total}")

        # Interação para faixa de páginas
        try:
            s = input("   Primeira página (Enter=1): ").strip()
            start = int(s) if s else 1
            s = input(f"   Última página (Enter={total}): ").strip()
            end = int(s) if s else total
            if not (1 <= start <= end <= total):
                raise ValueError
        except ValueError:
            print("   ❌ Faixa inválida; pulando.")
            continue

        trimmed = trim_pdf(pdf, INPUT_DIR, start_page=start, end_page=end)
        print(f"   ✅ Gravado em 'input/{trimmed.name}'")
        processed.add(periodo)
        new_count += 1

    # 4) Decidir se executa extração de movimentações
    # Sempre reexecuta se não houver CSV, ou se houve novos trims.
    run_parser = False
    if not CSV_PATH.is_file():
        run_parser = True
        print("\n▶️  CSV ausente; executando extração.")
    elif new_count > 0:
        run_parser = True
        print("\n▶️  Novos PDFs aparados; executando extração.")
    else:
        resp = (
            input("\nNenhum novo extrato aparado. Reexecutar extração? (s/n): ")
            .strip()
            .lower()
        )
        if resp == "s":
            run_parser = True

    if run_parser:
        # 5) Backup do CSV existente
        if CSV_PATH.is_file():
            backup_target = BACKUP_DIR / CSV_PATH.name
            CSV_PATH.replace(backup_target)
            print(f"✔️  CSV antigo movido para 'last_planilhas/{backup_target.name}'")
        # 6) Extrai e grava CSV
        rows = extract_all_movements(INPUT_DIR)
        if rows:
            write_movements_csv(rows, CSV_PATH)
        else:
            print("⚠️  Nenhuma transação extraída.")
    else:
        print("\nℹ️  Extração não executada; CSV permanece inalterado.")

    # 7) Relatório final
    if not CSV_PATH.is_file():
        sys.exit("❌ CSV não encontrado após execução.")

    df = pd.read_csv(CSV_PATH, dtype=str, encoding="utf-8")
    periodos = sorted(df["periodo"].dropna().unique(), key=periodo_to_date)

    print("\n📅 Períodos no CSV:")
    for p in periodos:
        print(f"   • {p}")

    gaps = list_gaps(periodos)
    if gaps:
        print("\n🚧 Lacunas detectadas:")
        for g in gaps:
            print(f"   • falta {g}")
    else:
        print("\n✅ Sem lacunas — períodos contíguos.")

    arquivos = set(df["arquivo"].dropna().unique())
    missing = [a for a in arquivos if not (INPUT_DIR / a).exists()]
    if missing:
        print("\n🗑 PDFs referenciados ausentes em 'input/':")
        for a in missing:
            per = df[df["arquivo"] == a]["periodo"].iloc[0]
            print(f"   • {a}  ({per})")
    else:
        print("\n✅ Todos os PDFs referenciados estão em 'input/'.")


if __name__ == "__main__":
    main()
