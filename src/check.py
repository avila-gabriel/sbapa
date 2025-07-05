"""
check_validation_modificado.py - Valida se cada conta prevista em **referencia.csv**
aparece no extrato (**movimentacoes.csv**) pelo mesmo valor e mês, sem reutilizar
linhas já alocadas.

Se existir mais de uma linha candidata no extrato, o script exibe a linha da
referência que está sendo conciliada e uma lista numerada de candidatos REAIS
(somente valores dentro de ± EPSILON). O usuário escolhe a opção correta
ou pressiona Enter para ignorar.

Gera **verificacao_saida.csv** com as colunas originais da referência +
    Encontrado (Sim/Não), Linha_extrato, valor_extrato, descricao_raw
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Optional, Set

import pandas as pd

# Configuração: tolerância para valor (R$)
EPSILON = 0.01


# Ajuda CLI
def mostrar_ajuda() -> None:
    print(
        """
check_validation_modificado.py
──────────────────────────────

Concilia lançamentos previstos (referencia.csv) com movimentos reais (movimentacoes.csv).
Uma escolha interativa só aparece quando há múltiplos candidatos compatíveis.

Uso:
    uv run -m check_validation_modificado
"""
    )
    sys.exit(0)


# Limpeza de DataFrame
def limpar_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    return df


# Converte valor da referência para float negativo
def parse_valor_ref(val) -> Optional[float]:
    if pd.isna(val):
        return None
    s = str(val).strip().replace("R$", "").replace(" ", "")
    parts = s.split(",")
    if len(parts) > 2:
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        return -abs(float(s))
    except ValueError:
        return None


# Exibe candidatos e lê escolha
def escolher_candidato(
    df_cands: pd.DataFrame, usados: Set[int], row_ref: pd.Series
) -> Optional[pd.Series]:
    # filtra já usados
    df_cands = df_cands[~df_cands.index.isin(usados)]
    if len(df_cands) <= 1:
        return df_cands.iloc[0] if not df_cands.empty else None

    # Interatividade somente se houver mais de um candidato
    print(f"\n🔎 Lançamento: Mês={row_ref['Mês']} Valor={row_ref['ValorNum']:.2f}")
    print("    Mais de um candidato encontrado. Escolha:")
    opcoes = []
    for idx, (ix, r) in enumerate(df_cands.iterrows(), start=1):
        print(
            f"      [{idx}] linha {ix} | data {r['data']} | valor {r['valor']:.2f} | {r['descricao_raw'][:60]}"
        )
        opcoes.append(r)

    escolha = input("      Número da opção (Enter para ignorar): ").strip()
    if escolha.isdigit():
        n = int(escolha)
        if 1 <= n <= len(opcoes):
            return opcoes[n - 1]
    return None


# Main
def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        mostrar_ajuda()

    # Caminhos
    base_dir = Path("planilhas")
    referencia_path = base_dir / "referencia.csv"
    extrato_path = base_dir / "movimentacoes.csv"
    saida_path = base_dir / "verificacao_saida.csv"

    # Garante que a pasta exista para salvar a saída
    saida_path.parent.mkdir(parents=True, exist_ok=True)

    # Carrega referência
    referencia_df = pd.read_csv(
        referencia_path, dtype=str, encoding="utf-8", skipinitialspace=True
    )
    referencia_df = limpar_df(referencia_df)
    referencia_df["ValorNum"] = referencia_df["Valor"].apply(parse_valor_ref)
    referencia_df = referencia_df.dropna(subset=["ValorNum"]).copy()
    referencia_df["Mês"] = referencia_df["Mês"].str.zfill(2)

    # Carrega extrato
    extrato_df = pd.read_csv(
        extrato_path,
        encoding="utf-8",
        engine="python",
        on_bad_lines="warn",
        quotechar='"',
    )
    extrato_df = limpar_df(extrato_df)
    extrato_df["valor"] = pd.to_numeric(extrato_df["valor"], errors="coerce")
    extrato_df = extrato_df.dropna(subset=["valor"]).copy()
    extrato_df["Mês"] = extrato_df["data"].str.split("/").str[1].str.zfill(2)

    usados: Set[int] = set()
    resultados = []

    for _, row in referencia_df.iterrows():
        valor = row["ValorNum"]
        mes = row["Mês"]
        # candidatos: mesmo mês e |valor_ref - valor| <= EPSILON
        mask = (
            (extrato_df["Mês"] == mes)
            & (~extrato_df.index.isin(usados))
            & (extrato_df["valor"].sub(valor).abs() <= EPSILON)
        )
        candidatos = extrato_df[mask]
        match = escolher_candidato(candidatos, usados, row)

        if match is not None:
            usados.add(match.name)
            resultados.append(
                {
                    **row.to_dict(),
                    "Encontrado": "Sim",
                    "Linha_extrato": int(match.name)
                    + 2,  # +2 p/ compensar cabeçalho (CSV + 0-based)
                    "valor_extrato": match["valor"],
                    "descricao_raw": match["descricao_raw"],
                }
            )
        else:
            resultados.append(
                {
                    **row.to_dict(),
                    "Encontrado": "Não",
                    "Linha_extrato": "",
                    "valor_extrato": "",
                    "descricao_raw": "",
                }
            )

    # grava saída
    colunas = list(referencia_df.columns) + [
        "Encontrado",
        "Linha_extrato",
        "valor_extrato",
        "descricao_raw",
    ]
    with open(saida_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=colunas)
        writer.writeheader()
        writer.writerows(resultados)

    print(
        f"\n✔️  Processamento concluído ({len(resultados)} itens). Saída: {saida_path}"
    )


if __name__ == "__main__":
    main()
