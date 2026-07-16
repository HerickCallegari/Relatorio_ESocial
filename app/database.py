from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.settings import settings


def init_data_dir() -> None:
    if settings.database_url.startswith("sqlite:///./data/"):
        Path("data").mkdir(exist_ok=True)


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        # WAL permite leitura (UI) concorrente com escrita (coleta), inclusive
        # entre processos. busy_timeout evita "database is locked" em concorrencia.
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")  # espera ate 10s por um lock
        cursor.execute("PRAGMA synchronous=NORMAL")  # seguro com WAL e mais rapido
        cursor.close()


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> None:
    """Migracao leve: adiciona colunas novas em tabelas ja existentes.

    O create_all() cria tabelas novas, mas nao altera as existentes.
    ALTER TABLE ADD COLUMN e suportado por SQLite e demais bancos.
    """
    inspector = inspect(engine)
    if "companies" not in inspector.get_table_names():
        return
    colunas = {col["name"] for col in inspector.get_columns("companies")}
    if "inconsistencias_atualizadas_em" not in colunas:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE companies ADD COLUMN inconsistencias_atualizadas_em DATETIME")
            )

