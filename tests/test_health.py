from tests.conftest import get_test_client


def test_health_check() -> None:
    client = get_test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
