from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import BlacklistedCompany, Company, User
from app.services.blacklist import add_to_blacklist, blacklisted_codes, remove_from_blacklist


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/blacklist")
def blacklist_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    blocked = blacklisted_codes(db)
    companies = (
        db.query(Company)
        .filter(Company.ativo.is_(True), Company.codigo_soc.notin_(blocked or {""}))
        .order_by(Company.nome.asc())
        .all()
    )
    items = db.query(BlacklistedCompany).order_by(BlacklistedCompany.codigo_soc.asc()).all()
    return templates.TemplateResponse(
        "blacklist.html",
        {
            "request": request,
            "current_user": current_user,
            "companies": companies,
            "items": items,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/blacklist")
def blacklist_add(
    company_codigo: str = Form(""),
    codigo_manual: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    codigo = (company_codigo or codigo_manual or "").strip()
    try:
        add_to_blacklist(db, codigo)
    except ValueError as exc:
        return RedirectResponse(f"/blacklist?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(
        "/blacklist?message=Empresa adicionada a blacklist e dados removidos.",
        status_code=303,
    )


@router.post("/blacklist/{item_id}/remove")
def blacklist_remove(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    remove_from_blacklist(db, item_id)
    return RedirectResponse("/blacklist?message=Empresa removida da blacklist.", status_code=303)
