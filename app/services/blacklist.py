from datetime import datetime

from sqlalchemy.orm import Session

from app.models import BlacklistedCompany, Company, Inconsistency, SyncLog


def is_blacklisted(db: Session, codigo_soc: str | None) -> bool:
    codigo = _clean_codigo(codigo_soc)
    if not codigo:
        return False
    return (
        db.query(BlacklistedCompany.id)
        .filter(BlacklistedCompany.codigo_soc == codigo)
        .first()
        is not None
    )


def blacklisted_codes(db: Session) -> set[str]:
    return {row[0] for row in db.query(BlacklistedCompany.codigo_soc).all()}


def add_to_blacklist(db: Session, codigo_soc: str, nome: str | None = None) -> BlacklistedCompany:
    codigo = _clean_codigo(codigo_soc)
    if not codigo:
        raise ValueError("Informe o codigo da empresa.")

    company = db.query(Company).filter(Company.codigo_soc == codigo).first()
    nome_final = _clean_nome(nome) or (company.nome if company else None) or (
        company.razao_social if company else None
    )

    item = (
        db.query(BlacklistedCompany)
        .filter(BlacklistedCompany.codigo_soc == codigo)
        .first()
    )
    if item:
        item.nome = nome_final or item.nome
    else:
        item = BlacklistedCompany(codigo_soc=codigo, nome=nome_final, created_at=datetime.utcnow())
        db.add(item)

    purge_company_data(db, codigo)
    db.commit()
    return item


def remove_from_blacklist(db: Session, item_id: int) -> None:
    item = db.get(BlacklistedCompany, item_id)
    if item:
        db.delete(item)
        db.commit()


def purge_company_data(db: Session, codigo_soc: str) -> None:
    codigo = _clean_codigo(codigo_soc)
    if not codigo:
        return
    db.query(Inconsistency).filter(Inconsistency.company_codigo_soc == codigo).delete(
        synchronize_session=False
    )
    db.query(SyncLog).filter(SyncLog.company_codigo_soc == codigo).delete(
        synchronize_session=False
    )
    db.query(Company).filter(Company.codigo_soc == codigo).delete(synchronize_session=False)


def _clean_codigo(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _clean_nome(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
