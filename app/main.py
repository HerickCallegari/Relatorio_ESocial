from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import Base, engine, ensure_schema, init_data_dir
from app.models import BulkSyncJob, User
from app.routes import auth, blacklist, dashboard, reports
from app.security import hash_password
from app.settings import settings
from app.database import SessionLocal


def create_app() -> FastAPI:
    init_data_dir()
    Base.metadata.create_all(bind=engine)
    ensure_schema()

    application = FastAPI(title="Relatorio de Inconsistencias eSocial")
    application.mount("/static", StaticFiles(directory="app/static"), name="static")
    application.include_router(auth.router)
    application.include_router(reports.router)
    application.include_router(dashboard.router)
    application.include_router(blacklist.router)

    @application.on_event("startup")
    def ensure_initial_admin() -> None:
        if not settings.admin_username or not settings.admin_password:
            return

        db = SessionLocal()
        try:
            exists = db.query(User).first()
            if exists:
                return
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=hash_password(settings.admin_password),
                    is_active=True,
                )
            )
            db.commit()
        finally:
            db.close()

    @application.on_event("startup")
    def marcar_jobs_orfaos() -> None:
        # Jobs presos em "running" (ex.: servidor reiniciou no meio) viram "interrompido".
        db = SessionLocal()
        try:
            orfaos = (
                db.query(BulkSyncJob)
                .filter(BulkSyncJob.status.in_(["running", "cancelando"]))
                .all()
            )
            for job in orfaos:
                job.status = "interrompido"
                job.finished_at = datetime.utcnow()
                job.updated_at = datetime.utcnow()
            if orfaos:
                db.commit()
        finally:
            db.close()

    @application.exception_handler(404)
    async def not_found(request: Request, exc: Exception):
        templates = Jinja2Templates(directory="app/templates")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "status_code": 404, "message": "Pagina nao encontrada."},
            status_code=404,
        )

    return application


app = create_app()
