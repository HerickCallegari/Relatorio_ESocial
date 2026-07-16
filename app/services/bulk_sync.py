"""Sincronizacao em massa de inconsistencias de todas as empresas ativas.

Regras respeitadas:
- Sequencial (o SOC proibe paralelismo).
- Isola erro por empresa (uma falha nao derruba o lote).
- Retomavel: pula empresas ja sincronizadas na janela recente.
- Trava de execucao unica (um job por vez).
- Cancelavel: status "cancelando" no banco faz o job parar no proximo item.
"""
import threading
import time
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import BulkSyncJob, Company
from app.services.blacklist import blacklisted_codes, is_blacklisted
from app.services.sync import sync_companies, sync_inconsistencies

PERIODO_DIAS = 60
PAUSA_ENTRE_EMPRESAS = 0.2  # segundos, para nao sobrecarregar o SOC
FRESCOR_HORAS = 12  # empresa sincronizada ha menos que isso e considerada "ja feita"

# Estados que indicam job vivo (para trava de execucao unica e cancelamento).
STATUS_ATIVOS = ("running", "cancelando")

_lock = threading.Lock()


def job_em_andamento(db: Session) -> BulkSyncJob | None:
    return (
        db.query(BulkSyncJob)
        .filter(BulkSyncJob.status.in_(STATUS_ATIVOS))
        .order_by(BulkSyncJob.id.desc())
        .first()
    )


def ultimo_job(db: Session) -> BulkSyncJob | None:
    return db.query(BulkSyncJob).order_by(BulkSyncJob.id.desc()).first()


def _criar_job() -> tuple[int | None, str]:
    """Cria o registro do job com a trava de execucao unica."""
    with _lock:
        db = SessionLocal()
        try:
            if job_em_andamento(db):
                return None, "Ja existe uma atualizacao em andamento."
            hoje = datetime.utcnow().date()
            job = BulkSyncJob(
                status="running",
                escopo="ativas",
                data_inicio=hoje - timedelta(days=PERIODO_DIAS),
                data_fim=hoje,
                started_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(job)
            db.commit()
            return job.id, "Atualizacao iniciada."
        finally:
            db.close()


def iniciar_bulk_sync() -> tuple[bool, str]:
    """Cria o job e dispara em thread de background (usado pelo botao da UI)."""
    job_id, msg = _criar_job()
    if job_id is None:
        return False, msg
    thread = threading.Thread(target=run_bulk_sync, args=(job_id,), daemon=True)
    thread.start()
    return True, "Atualizacao iniciada. Ela roda em segundo plano e pode levar horas."


def executar_bulk_sync_sincrono(
    limite: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[int | None, str]:
    """Cria o job e roda no processo atual (usado pelo script standalone)."""
    job_id, msg = _criar_job()
    if job_id is None:
        return None, msg
    run_bulk_sync(job_id, limite=limite, on_progress=on_progress)
    return job_id, "Concluido."


def _foi_cancelado(db: Session, job_id: int) -> bool:
    status = db.query(BulkSyncJob.status).filter(BulkSyncJob.id == job_id).scalar()
    return status == "cancelando"


def run_bulk_sync(
    job_id: int,
    limite: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """Executa o lote. Pode ser chamado por thread (botao) ou por script.

    limite: se informado, processa no maximo N empresas (testes/execucoes parciais).
    on_progress: callback (processadas, total) chamado apos cada empresa.
    """
    db = SessionLocal()
    db.expire_on_commit = False  # mantem a lista de empresas viva entre commits
    try:
        job = db.get(BulkSyncJob, job_id)
        if not job:
            return

        data_inicio = job.data_inicio
        data_fim = job.data_fim

        # Atualiza o cadastro de empresas ANTES de varrer as inconsistencias
        # (pega empresas novas/removidas). Se falhar, segue com o cadastro atual.
        try:
            sync_companies(db)
        except Exception as exc:
            db.rollback()
            job = db.get(BulkSyncJob, job_id)
            if job:
                job.mensagem = (
                    f"Aviso: falha ao sincronizar empresas; seguindo com o cadastro "
                    f"atual. ({str(exc)[:120]})"
                )
                job.updated_at = datetime.utcnow()
                db.commit()

        limite_frescor = datetime.utcnow() - timedelta(hours=FRESCOR_HORAS)
        blocked = blacklisted_codes(db)

        query = (
            db.query(Company)
            .filter(Company.ativo.is_(True))
            .order_by(Company.codigo_soc.asc())
        )
        if blocked:
            query = query.filter(Company.codigo_soc.notin_(blocked))
        if limite:
            query = query.limit(limite)
        empresas = query.all()

        job.total = len(empresas)
        job.updated_at = datetime.utcnow()
        db.commit()

        for company in empresas:
            # Cancelamento solicitado pela UI?
            if _foi_cancelado(db, job_id):
                job.status = "cancelado"
                job.empresa_atual = None
                job.finished_at = datetime.utcnow()
                job.updated_at = datetime.utcnow()
                job.mensagem = (
                    f"Cancelado em {job.processadas}/{job.total}: "
                    f"{job.total_inconsistencias} inconsistencias, {job.erros} erros."
                )
                db.commit()
                return

            # Retomada: pula quem ja foi sincronizada recentemente.
            if is_blacklisted(db, company.codigo_soc):
                job.processadas += 1
                job.updated_at = datetime.utcnow()
                db.commit()
                if on_progress:
                    on_progress(job.processadas, job.total)
                continue

            ja_feita = (
                company.inconsistencias_atualizadas_em
                and company.inconsistencias_atualizadas_em >= limite_frescor
            )
            if ja_feita:
                job.processadas += 1
                job.updated_at = datetime.utcnow()
                db.commit()
                if on_progress:
                    on_progress(job.processadas, job.total)
                continue

            job.empresa_atual = company.nome or company.razao_social or company.codigo_soc
            job.updated_at = datetime.utcnow()
            db.commit()

            try:
                count = sync_inconsistencies(db, company.codigo_soc, data_inicio, data_fim)
                job.total_inconsistencias += count
                company.inconsistencias_atualizadas_em = datetime.utcnow()
            except Exception as exc:
                # sync_inconsistencies ja fez rollback; apenas registra e segue.
                job.erros += 1
                job.mensagem = f"Ultimo erro ({company.codigo_soc}): {str(exc)[:200]}"
            finally:
                job.processadas += 1
                job.updated_at = datetime.utcnow()
                db.commit()
                if on_progress:
                    on_progress(job.processadas, job.total)

            time.sleep(PAUSA_ENTRE_EMPRESAS)

        job.status = "success"
        job.empresa_atual = None
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        job.mensagem = (
            f"Concluido: {job.total_inconsistencias} inconsistencias, {job.erros} erros."
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(BulkSyncJob, job_id)
        if job:
            job.status = "error"
            job.mensagem = f"Falha geral do lote: {str(exc)[:200]}"
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
