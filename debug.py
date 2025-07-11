import sys
from pathlib import Path

import pdfplumber

AVISO_ORIGEM = (
    "⚠️  Este PDF foi baixado do Santander — Extrato Consolidado Mensal."
    "\n    Caso você não reconheça o documento, interrompa a execução."
)


def resolve_pdf_path(raw_name: str) -> Path:
    """
    Recebe um nome passado pela CLI ou pela seleção e devolve um Path para o PDF dentro de ./input/:
      • Aceita com ou sem '.pdf'
      • Adiciona '.pdf' se faltar
    """
    p = Path("input") / raw_name
    if p.suffix.lower() != ".pdf":
        p = p.with_suffix(".pdf")
    return p


def choose_pdf_interactively() -> str:
    """Lista PDFs em ./input/ e retorna o nome (com extensão) escolhido."""
    directory = Path("input")
    if not directory.is_dir():
        print("❌ Diretório 'input/' não encontrado.")
        sys.exit(1)

    pdfs = sorted(directory.glob("*.pdf"))
    if not pdfs:
        print("❌ Não há PDFs em 'input/'.")
        sys.exit(0)

    print("Selecione um PDF para depurar:\n")
    for idx, pdf in enumerate(pdfs, start=1):
        print(f"[{idx}] {pdf.name}")

    choice = input("\nDigite o número do arquivo (Enter para cancelar): ").strip()
    if not choice.isdigit() or not (1 <= (n := int(choice)) <= len(pdfs)):
        print("❌ Seleção inválida, saindo.")
        sys.exit(1)

    return pdfs[n - 1].name


def main() -> None:
    # 1) Determine which file to open
    if len(sys.argv) == 1:
        raw_name = choose_pdf_interactively()
    elif len(sys.argv) == 2:
        raw_name = sys.argv[1]
    else:
        print("❌ Uso incorreto.")
        print("✅ Executar assim: uv run -m debug_pdf [<nome_do_arquivo>.pdf]")
        sys.exit(1)

    pdf_path = resolve_pdf_path(raw_name)

    # 2) Warnings & existence checks
    print(AVISO_ORIGEM, end="\n\n")

    if not pdf_path.is_file():
        print(f"❌ Arquivo '{pdf_path}' não encontrado.")
        sys.exit(1)

    if pdf_path.suffix.lower() != ".pdf":
        print("❌ O arquivo informado não é um PDF.")
        sys.exit(1)

    # 3) Extract & print text only
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                print("⚠️  O PDF não contém páginas.")
                sys.exit(1)

            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    print(text)

    except Exception as err:
        print(f"❌ Erro ao processar '{pdf_path.name}': {err}")
        sys.exit(1)

    print("\n" + AVISO_ORIGEM)


if __name__ == "__main__":
    main()
