from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Company, Inconsistency, User
from app.services.blacklist import blacklisted_codes, is_blacklisted
from app.services.bulk_sync import iniciar_bulk_sync, job_em_andamento, ultimo_job
from app.services.soc_client import SocClientError
from app.services.sync import sync_companies, sync_inconsistencies


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@router.get("/")
def report_page(
    request: Request,
    empresa_codigo: str | None = Query(default=None),
    funcionario: str | None = Query(default=None),
    setor: str | None = Query(default=None),
    cargo: str | None = Query(default=None),
    leiaute: str | None = Query(default=None),
    inconsistencia: str | None = Query(default=None),
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    empresa_codigo = _clean(empresa_codigo)
    funcionario = _clean(funcionario)
    setor = _clean(setor)
    cargo = _clean(cargo)
    leiaute = _clean(leiaute)
    inconsistencia = _clean(inconsistencia)
    di = _parse_date(data_inicio)
    df = _parse_date(data_fim)
    blocked = blacklisted_codes(db)

    def apply_filters(base, *, exclude: str | None = None):
        if blocked:
            base = base.filter(Inconsistency.company_codigo_soc.notin_(blocked))
        # empresa/funcionario/datas sempre restringem (nao sao dropdowns).
        if empresa_codigo:
            base = base.filter(Inconsistency.company_codigo_soc == empresa_codigo)
        if funcionario:
            base = base.filter(Inconsistency.nome_funcionario.ilike(f"%{funcionario}%"))
        if di:
            base = base.filter(func.date(Inconsistency.created_at) >= di.isoformat())
        if df:
            base = base.filter(func.date(Inconsistency.created_at) <= df.isoformat())
        # cada dropdown restringe, exceto quando estamos calculando as opcoes dele.
        if setor and exclude != "setor":
            base = base.filter(Inconsistency.nome_setor == setor)
        if cargo and exclude != "cargo":
            base = base.filter(Inconsistency.nome_cargo == cargo)
        if leiaute and exclude != "leiaute":
            base = base.filter(Inconsistency.leiaute == leiaute)
        if inconsistencia and exclude != "inconsistencia":
            base = base.filter(Inconsistency.descricao_inconsistencia == inconsistencia)
        return base

    def facet(column, key: str) -> list[str]:
        # Opcoes dinamicas: valores distintos aplicando todos os filtros MENOS o proprio.
        rows = (
            apply_filters(db.query(column), exclude=key)
            .filter(column.isnot(None), column != "")
            .distinct()
            .order_by(column.asc())
            .all()
        )
        return [row[0] for row in rows]

    inconsistencies = (
        apply_filters(db.query(Inconsistency))
        .order_by(Inconsistency.updated_at.desc())
        .limit(500)
        .all()
    )

    return templates.TemplateResponse(
        "report.html",
        {
            "request": request,
            "current_user": current_user,
            "companies": (
                db.query(Company)
                .filter(Company.codigo_soc.notin_(blocked or {""}))
                .order_by(Company.nome.asc())
                .all()
            ),
            "inconsistencies": inconsistencies,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
            "bulk_job": ultimo_job(db),
            # valores selecionados nos filtros (para repopular o formulario)
            "f_empresa_codigo": empresa_codigo or "",
            "f_funcionario": funcionario or "",
            "f_setor": setor or "",
            "f_cargo": cargo or "",
            "f_leiaute": leiaute or "",
            "f_inconsistencia": inconsistencia or "",
            "f_data_inicio": data_inicio or "",
            "f_data_fim": data_fim or "",
            # opcoes dinamicas (facetadas) dos dropdowns
            "opt_setores": facet(Inconsistency.nome_setor, "setor"),
            "opt_cargos": facet(Inconsistency.nome_cargo, "cargo"),
            "opt_leiautes": facet(Inconsistency.leiaute, "leiaute"),
            "opt_inconsistencias": facet(Inconsistency.descricao_inconsistencia, "inconsistencia"),
        },
    )


@router.post("/companies/sync")
def companies_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        count = sync_companies(db)
    except SocClientError as exc:
        return RedirectResponse(f"/?error={quote(str(exc))}", status_code=303)
    except Exception:
        return RedirectResponse("/?error=Falha ao sincronizar empresas.", status_code=303)
    return RedirectResponse(f"/?message={quote(f'{count} empresas sincronizadas.')}", status_code=303)


@router.post("/inconsistencies/sync")
def inconsistencies_sync(
    company_codigo: str = Form(...),
    data_inicio: date = Form(...),
    data_fim: date = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if (data_fim - data_inicio).days > 60:
        return RedirectResponse("/?error=O periodo maximo permitido pelo SOC e de 60 dias.", status_code=303)
    if data_fim < data_inicio:
        return RedirectResponse("/?error=A data final deve ser maior ou igual a data inicial.", status_code=303)
    if is_blacklisted(db, company_codigo):
        return RedirectResponse("/?error=Empresa esta na blacklist e nao pode ser consultada.", status_code=303)

    try:
        count = sync_inconsistencies(db, company_codigo, data_inicio, data_fim)
    except SocClientError as exc:
        return RedirectResponse(f"/?error={quote(str(exc))}", status_code=303)
    except ValueError as exc:
        return RedirectResponse(f"/?error={quote(str(exc))}", status_code=303)
    except Exception:
        return RedirectResponse("/?error=Falha ao atualizar inconsistencias.", status_code=303)

    return RedirectResponse(
        f"/?company={quote(company_codigo)}&message={quote(f'{count} inconsistencias atualizadas.')}",
        status_code=303,
    )


@router.post("/inconsistencies/sync-all")
def inconsistencies_sync_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    iniciado, msg = iniciar_bulk_sync()
    chave = "message" if iniciado else "error"
    return RedirectResponse(f"/?{chave}={quote(msg)}", status_code=303)


@router.get("/inconsistencies/sync-all/status")
def sync_all_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = ultimo_job(db)
    if not job:
        return {"status": "none"}
    return {
        "status": job.status,
        "processadas": job.processadas,
        "total": job.total,
        "empresa_atual": job.empresa_atual,
        "total_inconsistencias": job.total_inconsistencias,
        "erros": job.erros,
    }


@router.post("/inconsistencies/sync-all/cancel")
def inconsistencies_sync_cancel(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = job_em_andamento(db)
    if not job:
        return RedirectResponse(
            f"/?error={quote('Nenhuma atualizacao em andamento.')}", status_code=303
        )
    if job.status != "cancelando":
        job.status = "cancelando"
        job.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(
        f"/?message={quote('Cancelamento solicitado. O job vai parar em instantes.')}",
        status_code=303,
    )
