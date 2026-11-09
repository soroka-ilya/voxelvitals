"""Global pytest configuration ensuring all tests use an isolated temporary database."""

import os
import pytest
from app.config import settings
from app.api import api_routes, oauth_routes, routes
import app.main as main
import app.services.tg_service as tg_service


@pytest.fixture(scope="session", autouse=True)
def configure_test_db(tmp_path_factory):
    """Point database to an isolated temporary file for the entire test session."""
    temp_dir = tmp_path_factory.mktemp("test_db")
    test_db_path = str(temp_dir / "test_isolated.db")

    settings.db_path = test_db_path
    os.environ["DB_PATH"] = test_db_path

    for mod in (api_routes, oauth_routes, routes, main, tg_service):
        if hasattr(mod, "repo"):
            mod.repo.db_path = test_db_path

    yield test_db_path

    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass
