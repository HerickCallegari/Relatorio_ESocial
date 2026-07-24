from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import Company, Inconsistency, SyncLog
from app.services.blacklist import blacklisted_codes, is_blacklisted
from app.services.normalizers import normalize_company, normalize_inconsistency
from app.services.soc_client import SocClientError, soc_client
from app.settings import settings

# O Exporta Dados 205226 exige o campo leiauteEsocial. Os 4 codigos podem ser
# enviados juntos (separados por virgula) numa unica chamada, que agrega todos os
# tipos — o leiaute de cada linha vem na coluna LEIAUTE da resposta.
LEIAUTES_205226 = {
    "5": "S-2210",
    "1": "S-2220",
    "15": "S-2221",
    "6": "S-2230",
}
LEIAUTES_205226_COMBINADO = ",".join(LEIAUTES_205226)


def sync_companies(db: Session) -> int:
    log = SyncLog(tipo="companies", status="running", started_at=datetime.utcnow())
    db.add(log)
    db.commit()

    try:
        rows = soc_client.export_data(
            {
                "empresa": settings.soc_empresa,
                "codigo": settings.soc_empresas_codigo,
                "chave": settings.soc_empresas_chave,
                "tipoSaida": "json",
            }
        )
        count = 0
        blocked = blacklisted_codes(db)
        for row in rows:
            data = normalize_company(row)
            if not data:
                continue
            if data["codigo_soc"] in blocked:
                continue
            company = db.query(Company).filter(Company.codigo_soc == data["codigo_soc"]).first()
            if company:
                for key, value in data.items():
                    setattr(company, key, value)
                company.updated_at = datetime.utcnow()
            else:
                db.add(Company(**data, updated_at=datetime.utcnow()))
            count += 1

        log.status = "success"
        log.mensagem = f"{count} empresas sincronizadas."
        log.finished_at = datetime.utcnow()
        db.commit()
        return count
    except SocClientError as exc:
        # Mensagem ja sanitizada pelo SocClient (sem URL/chave).
        db.rollback()
        log.status = "error"
        log.mensagem = str(exc)
        log.finished_at = datetime.utcnow()
        db.add(log)
        db.commit()
        raise
    except Exception:
        # Nao gravar str(exc) cru: pode conter URL/parametros com a chave.
        db.rollback()
        log.status = "error"
        log.mensagem = "Erro interno ao processar a sincronizacao."
        log.finished_at = datetime.utcnow()
        db.add(log)
        db.commit()
        raise


def sync_inconsistencies(
    db: Session,
    company_codigo: str,
    data_inicio: date,
    data_fim: date,
) -> int:
    if is_blacklisted(db, company_codigo):
        raise ValueError("Empresa esta na blacklist e nao pode ser consultada.")

    company = db.query(Company).filter(Company.codigo_soc == company_codigo).first()
    if not company:
        raise ValueError("Empresa nao encontrada.")

    log = SyncLog(
        tipo="inconsistencies",
        company_codigo_soc=company_codigo,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(log)
    db.commit()

    try:
        rows: list[tuple[str, str, dict]] = []
        rows.extend(_fetch_205226(company_codigo, data_inicio, data_fim))
        rows.extend(_fetch_218017(company_codigo, data_inicio, data_fim))

        origens = [
            settings.soc_inconsistencias_gerais_codigo,
            settings.soc_inconsistencias_2240_codigo,
        ]

        # Normaliza os registros vindos do SOC (objetos transitorios em memoria).
        novos: list[Inconsistency] = []
        for origem_exporta, leiaute_label, row in rows:
            item = normalize_inconsistency(row, company, origem_exporta, leiaute_label)
            if item:
                novos.append(item)

        def identidade(inc: Inconsistency):
            return (
                inc.company_codigo_soc,
                inc.codigo_funcionario,
                inc.data,
                inc.leiaute,
                inc.descricao_inconsistencia,
            )

        novos_por_id = {identidade(i): i for i in novos}
        existentes = (
            db.query(Inconsistency)
            .filter(
                Inconsistency.company_codigo_soc == company_codigo,
                Inconsistency.origem_exporta.in_(origens),
            )
            .all()
        )
        existentes_por_id = {identidade(e): e for e in existentes}
        agora = datetime.utcnow()

        # Remove as que nao voltaram do SOC (resolvidas).
        for chave, existente in existentes_por_id.items():
            if chave not in novos_por_id:
                db.delete(existente)

        # Mescla: mantem as ja existentes (preserva created_at = 1a puxada);
        # insere as novas (created_at = agora).
        for chave, novo in novos_por_id.items():
            existente = existentes_por_id.get(chave)
            if existente is None:
                db.add(novo)  # created_at default = agora (primeira vez vista)
            else:
                # atualiza campos descritivos, mas NAO mexe no created_at.
                existente.nome_empresa = novo.nome_empresa
                existente.codigo_unidade = novo.codigo_unidade
                existente.nome_unidade = novo.nome_unidade
                existente.codigo_setor = novo.codigo_setor
                existente.nome_setor = novo.nome_setor
                existente.codigo_cargo = novo.codigo_cargo
                existente.nome_cargo = novo.nome_cargo
                existente.nome_funcionario = novo.nome_funcionario
                existente.situacao_funcionario = novo.situacao_funcionario
                existente.raw_payload = novo.raw_payload
                existente.updated_at = agora

        count = len(novos_por_id)

        log.status = "success"
        log.mensagem = f"{count} inconsistencias sincronizadas."
        log.finished_at = datetime.utcnow()
        db.commit()
        return count
    except SocClientError as exc:
        db.rollback()
        log.status = "error"
        log.mensagem = str(exc)
        log.finished_at = datetime.utcnow()
        db.add(log)
        db.commit()
        raise
    except Exception:
        db.rollback()
        log.status = "error"
        log.mensagem = "Erro interno ao processar a sincronizacao."
        log.finished_at = datetime.utcnow()
        db.add(log)
        db.commit()
        raise


def _inconsistency_payload(
    code: str,
    key: str,
    company_codigo: str,
    data_inicio: date,
    data_fim: date,
    leiaute_esocial: str | None = None,
) -> dict[str, str]:
    payload = {
        "empresa": settings.soc_empresa,
        "codigo": code,
        "chave": key,
        "tipoSaida": "json",
        "empresaTrabalho": company_codigo,
        "unidade": "",
        "setor": "",
        "situacaoFuncionario": "",
        "dataInicio": data_inicio.strftime("%d/%m/%Y"),
        "dataFim": data_fim.strftime("%d/%m/%Y"),
    }
    if leiaute_esocial is not None:
        payload["leiauteEsocial"] = leiaute_esocial
    return payload


def _fetch_205226(
    company_codigo: str,
    data_inicio: date,
    data_fim: date,
) -> list[tuple[str, str | None, dict]]:
    # Uma unica chamada com os 4 leiautes juntos; o tipo de cada linha vem na
    # coluna LEIAUTE da resposta (tratada pelo normalizador).
    code = settings.soc_inconsistencias_gerais_codigo
    key = settings.soc_inconsistencias_gerais_chave
    payload = _inconsistency_payload(
        code, key, company_codigo, data_inicio, data_fim, LEIAUTES_205226_COMBINADO
    )
    return [(code, None, row) for row in soc_client.export_data(payload)]


def _fetch_218017(
    company_codigo: str,
    data_inicio: date,
    data_fim: date,
) -> list[tuple[str, str, dict]]:
    # S-2240: chamada unica, sem leiauteEsocial.
    code = settings.soc_inconsistencias_2240_codigo
    key = settings.soc_inconsistencias_2240_chave
    payload = _inconsistency_payload(code, key, company_codigo, data_inicio, data_fim)
    return [(code, "S-2240", row) for row in soc_client.export_data(payload)]
