from alembic import context
from sqlalchemy import create_engine

from app.core.config import load_settings

url = load_settings().database_url
if not url:
    raise SystemExit("Thiếu DATABASE_URL")


def run_migrations_online():
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
