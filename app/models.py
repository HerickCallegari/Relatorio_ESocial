from datetime import datetime, date

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo_soc: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    razao_social: Mapped[str | None] = mapped_column(String(250), nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    codigo_cliente_integracao: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Momento do ultimo sync de inconsistencias bem-sucedido (para retomada do lote).
    inconsistencias_atualizadas_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BlacklistedCompany(Base):
    __tablename__ = "blacklisted_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo_soc: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    nome: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Inconsistency(Base):
    __tablename__ = "inconsistencies"
    __table_args__ = (
        UniqueConstraint(
            "company_codigo_soc",
            "codigo_funcionario",
            "data",
            "leiaute",
            "descricao_inconsistencia",
            name="uq_inconsistency_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_codigo_soc: Mapped[str] = mapped_column(String(30), index=True)
    nome_empresa: Mapped[str | None] = mapped_column(String(250), nullable=True)
    codigo_unidade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    nome_unidade: Mapped[str | None] = mapped_column(String(200), nullable=True)
    codigo_setor: Mapped[str | None] = mapped_column(String(50), nullable=True)
    nome_setor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    codigo_cargo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    nome_cargo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    codigo_funcionario: Mapped[str | None] = mapped_column(String(50), nullable=True)
    nome_funcionario: Mapped[str | None] = mapped_column(String(200), nullable=True)
    situacao_funcionario: Mapped[str | None] = mapped_column(String(80), nullable=True)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    leiaute: Mapped[str | None] = mapped_column(String(30), nullable=True)
    descricao_inconsistencia: Mapped[str] = mapped_column(Text)
    origem_exporta: Mapped[str] = mapped_column(String(20), index=True)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BulkSyncJob(Base):
    __tablename__ = "bulk_sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # running | success | error | interrompido
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    escopo: Mapped[str] = mapped_column(String(20), default="ativas")
    total: Mapped[int] = mapped_column(Integer, default=0)
    processadas: Mapped[int] = mapped_column(Integer, default=0)
    total_inconsistencias: Mapped[int] = mapped_column(Integer, default=0)
    erros: Mapped[int] = mapped_column(Integer, default=0)
    empresa_atual: Mapped[str | None] = mapped_column(String(250), nullable=True)
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tipo: Mapped[str] = mapped_column(String(50))
    company_codigo_soc: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
