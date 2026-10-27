from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text


def upgrade_database(engine: Engine) -> None:
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as connection:
        # Serialize startup migrations across processes using this database.
        connection.execute(text("SELECT pg_advisory_xact_lock(784523901)"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
