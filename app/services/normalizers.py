import json
import re
from datetime import date, datetime
from typing import Any

from app.models import Company, Inconsistency


def normalize_leiaute(raw: str | None) -> str | None:
    """Padroniza o codigo do leiaute para o formato 'S-XXXX'.

    O 205226 devolve 'S2220' (sem hifen); o 218017 usamos 'S-2240'.
    """
    if not raw:
        return None
    texto = str(raw).strip().upper()
    match = re.match(r"S[-\s]?(\d{3,4})", texto)
    if match:
        return f"S-{match.group(1)}"
    return texto


def value(row: dict[str, Any], *keys: str) -> str | None:
    normalized = {str(key).upper(): item for key, item in row.items()}
    for key in keys:
        item = normalized.get(key.upper())
        if item not in (None, ""):
            return str(item).strip()
    return None


def parse_soc_date(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def normalize_company(row: dict[str, Any]) -> dict[str, Any] | None:
    codigo = value(row, "CODIGO")
    if not codigo:
        return None
    ativo = value(row, "ATIVO")
    return {
        "codigo_soc": codigo,
        "nome": value(row, "NOMEABREVIADO", "APELIDO", "NOME"),
        "razao_social": value(row, "RAZAOSOCIAL", "RAZAOSOCIALINICIAL"),
        "cnpj": value(row, "CNPJ"),
        "ativo": ativo != "0",
        "codigo_cliente_integracao": value(row, "CODIGOCLIENTEINTEGRACAO", "CÓD. CLIENTE (INT.)"),
    }


def normalize_inconsistency(
    row: dict[str, Any],
    company: Company,
    origem_exporta: str,
    leiaute_label: str | None = None,
) -> Inconsistency | None:
    descricao = value(row, "DESCRICAO_INCONSISTENCIA")
    if not descricao:
        return None

    # A coluna LEIAUTE nem sempre vem na resposta; usa o rotulo do que foi consultado.
    leiaute = normalize_leiaute(value(row, "LEIAUTE") or leiaute_label)

    return Inconsistency(
        company_codigo_soc=company.codigo_soc,
        nome_empresa=value(row, "NOME_EMPRESA") or company.nome or company.razao_social,
        codigo_unidade=value(row, "CODIGO_UNIDADE"),
        nome_unidade=value(row, "NOME_UNIDADE"),
        codigo_setor=value(row, "CODIGO_SETOR"),
        nome_setor=value(row, "NOME_SETOR"),
        codigo_cargo=value(row, "CODIGO_CARGO"),
        nome_cargo=value(row, "NOME_CARGO"),
        codigo_funcionario=value(row, "CODIGO_FUNCIONARIO"),
        nome_funcionario=value(row, "NOME_FUNCIONARIO", "NOME_FUNCIONÁRIO"),
        situacao_funcionario=value(row, "SITUACAO_FUNCIONARIO", "SITUACAO_DO_FUNCIONARIO"),
        data=parse_soc_date(value(row, "DATA")),
        leiaute=leiaute,
        descricao_inconsistencia=descricao,
        origem_exporta=origem_exporta,
        raw_payload=json.dumps(row, ensure_ascii=False),
    )

