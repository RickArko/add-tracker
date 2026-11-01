from alembic import context

from app.config import load_settings
from app.db import make_engine
from app.models import Base

db_url = context.config.attributes.get("db_url") or load_settings().db_url
engine = make_engine(db_url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
