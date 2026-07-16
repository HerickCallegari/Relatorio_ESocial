"""Executa o sync em massa de inconsistencias em PROCESSO PROPRIO (isolado do servidor web).

Assim voce pode reiniciar/editar o app (uvicorn --reload) sem interromper a coleta,
que continua rodando aqui. A UI acompanha o progresso lendo o mesmo banco.

Uso (a partir da raiz do projeto C:\\SafeWork\\ESocial):
    .\\.venv\\Scripts\\python scripts\\run_bulk_sync.py            # todas as empresas ativas
    .\\.venv\\Scripts\\python scripts\\run_bulk_sync.py --limite 5 # apenas N empresas (teste)

Cancelamento: clique em "Cancelar" na tela do app (ou defina o job como 'cancelando');
este processo para no proximo item.
"""
import argparse
import os
import sys

# Permite rodar de qualquer diretorio: garante o pacote 'app' no path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, engine, ensure_schema, init_data_dir  # noqa: E402
from app.services.bulk_sync import executar_bulk_sync_sincrono  # noqa: E402


def _imprimir_progresso(processadas: int, total: int) -> None:
    # Imprime a cada 25 empresas (e na ultima) para nao poluir o terminal.
    if total and (processadas % 25 == 0 or processadas == total):
        pct = (processadas / total * 100) if total else 0
        print(f"  progresso: {processadas}/{total} ({pct:.1f}%)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync em massa de inconsistencias (processo isolado do servidor web)."
    )
    parser.add_argument(
        "--limite", type=int, default=None, help="Maximo de empresas (para teste)."
    )
    args = parser.parse_args()

    init_data_dir()
    Base.metadata.create_all(bind=engine)
    ensure_schema()

    print("Iniciando sync em massa (empresas ativas, ultimos 60 dias)...", flush=True)
    job_id, msg = executar_bulk_sync_sincrono(limite=args.limite, on_progress=_imprimir_progresso)
    if job_id is None:
        print(f"Nao iniciado: {msg}", flush=True)
        sys.exit(1)
    print(f"Job {job_id}: {msg}", flush=True)


if __name__ == "__main__":
    main()
