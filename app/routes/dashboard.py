from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Inconsistency, User
from app.services.blacklist import blacklisted_codes
from app.services.bulk_sync import ultimo_job
from app.services.normalizers import normalize_leiaute

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Os 5 leiautes do eSocial cobertos — sempre exibidos (0 quando nao houver).
LEIAUTES_FIXOS = ["S-2210", "S-2220", "S-2221", "S-2230", "S-2240"]


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


@router.get("/dashboard")
def dashboard(
    request: Request,
    empresa_codigo: str | None = Query(default=None),
    leiaute: str | None = Query(default=None),
    inconsistencia: str | None = Query(default=None),
    data_inicio: str | None = Query(default=None),
    data_fim: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    empresa_codigo = _clean(empresa_codigo)
    leiaute_sel = _clean(leiaute)
    inconsistencia_sel = _clean(inconsistencia)
    di = _parse_date(data_inicio)
    df = _parse_date(data_fim)
    blocked = blacklisted_codes(db)

    def aplicar(query):
        if blocked:
            query = query.filter(Inconsistency.company_codigo_soc.notin_(blocked))
        if empresa_codigo:
            query = query.filter(Inconsistency.company_codigo_soc == empresa_codigo)
        if leiaute_sel:
            # cobre variantes tipo "S-2220"/"S2220"
            variantes = {leiaute_sel, leiaute_sel.replace("-", "")}
            query = query.filter(Inconsistency.leiaute.in_(variantes))
        if inconsistencia_sel:
            query = query.filter(Inconsistency.descricao_inconsistencia == inconsistencia_sel)
        if di:
            query = query.filter(Inconsistency.data >= di)
        if df:
            query = query.filter(Inconsistency.data <= df)
        return query

    total = aplicar(db.query(func.count(Inconsistency.id))).scalar() or 0
    empresas_afetadas = (
        aplicar(db.query(func.count(func.distinct(Inconsistency.company_codigo_soc)))).scalar() or 0
    )
    funcionarios_afetados = (
        aplicar(
            db.query(func.count(func.distinct(Inconsistency.codigo_funcionario))).filter(
                Inconsistency.codigo_funcionario.isnot(None),
                Inconsistency.codigo_funcionario != "",
            )
        ).scalar()
        or 0
    )

    # Por leiaute — sempre os 5 layouts (0 quando nao houver).
    raw_leiaute = (
        aplicar(db.query(Inconsistency.leiaute, func.count(Inconsistency.id)))
        .group_by(Inconsistency.leiaute)
        .all()
    )
    contagem: dict[str, int] = {}
    for le, n in raw_leiaute:
        chave = normalize_leiaute(le)
        if chave:
            contagem[chave] = contagem.get(chave, 0) + n
    total_leiaute = sum(contagem.get(le, 0) for le in LEIAUTES_FIXOS)
    leiaute_bars = [
        {
            "leiaute": le,
            "n": contagem.get(le, 0),
            "pct": (contagem.get(le, 0) / total_leiaute * 100) if total_leiaute else 0,
        }
        for le in LEIAUTES_FIXOS
    ]
    max_leiaute = max([b["n"] for b in leiaute_bars], default=0)

    # Por empresa (barras).
    top_empresas = (
        aplicar(db.query(Inconsistency.nome_empresa, func.count(Inconsistency.id)))
        .group_by(Inconsistency.nome_empresa)
        .order_by(func.count(Inconsistency.id).desc())
        .all()
    )
    top_empresas = [(nome or "(sem nome)", n) for nome, n in top_empresas]
    max_empresa = max([n for _, n in top_empresas], default=0)

    # Por tipo de inconsistencia (barras).
    top_tipos = (
        aplicar(db.query(Inconsistency.descricao_inconsistencia, func.count(Inconsistency.id)))
        .group_by(Inconsistency.descricao_inconsistencia)
        .order_by(func.count(Inconsistency.id).desc())
        .all()
    )
    max_tipo = max([n for _, n in top_tipos], default=0)

    # Opcoes do dropdown de inconsistencia (todas as descricoes distintas).
    opt_inconsistencias = [
        row[0]
        for row in db.query(Inconsistency.descricao_inconsistencia)
        .filter(
            Inconsistency.descricao_inconsistencia.isnot(None),
            Inconsistency.descricao_inconsistencia != "",
        )
        .distinct()
        .order_by(Inconsistency.descricao_inconsistencia.asc())
        .all()
    ]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "total": total,
            "empresas_afetadas": empresas_afetadas,
            "funcionarios_afetados": funcionarios_afetados,
            "leiaute_bars": leiaute_bars,
            "max_leiaute": max_leiaute,
            "top_empresas": top_empresas,
            "max_empresa": max_empresa,
            "top_tipos": top_tipos,
            "max_tipo": max_tipo,
            "bulk_job": ultimo_job(db),
            # filtros
            "leiautes_fixos": LEIAUTES_FIXOS,
            "opt_inconsistencias": opt_inconsistencias,
            "f_empresa_codigo": empresa_codigo or "",
            "f_leiaute": leiaute_sel or "",
            "f_inconsistencia": inconsistencia_sel or "",
            "f_data_inicio": data_inicio or "",
            "f_data_fim": data_fim or "",
        },
    )
