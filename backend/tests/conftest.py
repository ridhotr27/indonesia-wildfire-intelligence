import pytest
from fastapi.testclient import TestClient

from wildfire_api.core.config import Settings
from wildfire_api.main import create_app


@pytest.fixture
def client() -> TestClient:
    settings = Settings(
        environment="test",
        log_level="WARNING",
        max_geojson_features=2,
        max_date_range_days=366,
        semantic_routing_mode="disabled",
        embedding_provider="hashing",
    )
    with TestClient(create_app(settings=settings)) as test_client:
        yield test_client
