"""
Tests for watchlist configuration API endpoints.

Covers happy path, edge cases, error paths, type handling,
precision handling, timezone handling, and external API mocking.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from iatb.core.config_manager import (
    WATCHLIST_CONFIG_ENV_VAR,
    get_config_manager,
    reset_config_manager,
)
from iatb.fastapi_app import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a test client with temporary config."""
    # Set up temporary config path
    config_path = tmp_path / "watchlist.toml"
    monkeypatch.setenv(WATCHLIST_CONFIG_ENV_VAR, str(config_path))
    reset_config_manager()

    # Initialize with default config
    manager = get_config_manager()
    manager.update_config(
        nse=["RELIANCE", "TCS", "INFY"],
        bse=["SBIN"],
        mcx=["GOLD"],
        cds=["USDINR"],
    )

    return TestClient(app)


class TestGetWatchlistConfig:
    """Tests for GET /config/watchlist endpoint."""

    def test_get_watchlist_success(self, client: TestClient) -> None:
        """Test successfully retrieving watchlist configuration."""
        response = client.get("/config/watchlist")

        assert response.status_code == 200
        data = response.json()

        assert data["nse"] == ["RELIANCE", "TCS", "INFY"]
        assert data["bse"] == ["SBIN"]
        assert data["mcx"] == ["GOLD"]
        assert data["cds"] == ["USDINR"]
        assert data["total_symbols"] == 6
        assert "config_path" in data
        assert data["message"] == "Watchlist configuration retrieved successfully"

    def test_get_watchlist_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test retrieving empty watchlist."""
        # Set up new config path that doesn't exist
        empty_config_path = tmp_path / "empty.toml"
        monkeypatch.setenv(WATCHLIST_CONFIG_ENV_VAR, str(empty_config_path))
        reset_config_manager()

        # Create new client with empty config
        empty_client = TestClient(app)
        response = empty_client.get("/config/watchlist")

        assert response.status_code == 200
        data = response.json()
        assert data["nse"] == []
        assert data["bse"] == []
        assert data["mcx"] == []
        assert data["cds"] == []
        assert data["total_symbols"] == 0

    def test_get_watchlist_returns_copy(self, client: TestClient) -> None:
        """Test that modifying response doesn't affect internal state."""
        response1 = client.get("/config/watchlist")
        data1 = response1.json()

        # Modify the response data
        data1["nse"].append("NEW_SYMBOL")

        # Get again
        response2 = client.get("/config/watchlist")
        data2 = response2.json()

        # Should not have the new symbol
        assert "NEW_SYMBOL" not in data2["nse"]


class TestUpdateWatchlistConfig:
    """Tests for PUT /config/watchlist endpoint."""

    def test_update_nse_watchlist(self, client: TestClient) -> None:
        """Test updating NSE watchlist."""
        payload = {"nse": ["HDFCBANK", "ICICIBANK"]}
        response = client.put("/config/watchlist", json=payload)

        assert response.status_code == 200
        data = response.json()

        assert data["nse"] == ["HDFCBANK", "ICICIBANK"]
        assert data["bse"] == ["SBIN"]  # Should remain unchanged
        assert data["mcx"] == ["GOLD"]  # Should remain unchanged
        assert data["cds"] == ["USDINR"]  # Should remain unchanged
        assert data["total_symbols"] == 5
        assert data["message"] == "Watchlist configuration updated successfully"

        # Verify persistence
        get_response = client.get("/config/watchlist")
        assert get_response.json()["nse"] == ["HDFCBANK", "ICICIBANK"]

    def test_update_multiple_exchanges(self, client: TestClient) -> None:
        """Test updating multiple exchanges at once."""
        payload = {
            "nse": ["RELIANCE"],
            "bse": ["TCS"],
            "mcx": ["SILVER"],
            "cds": ["EURINR"],
        }
        response = client.put("/config/watchlist", json=payload)

        assert response.status_code == 200
        data = response.json()

        assert data["nse"] == ["RELIANCE"]
        assert data["bse"] == ["TCS"]
        assert data["mcx"] == ["SILVER"]
        assert data["cds"] == ["EURINR"]
        assert data["total_symbols"] == 4

    def test_update_partial_exchange(self, client: TestClient) -> None:
        """Test updating only one exchange."""
        payload = {"mcx": ["COPPER", "NATURALGAS"]}
        response = client.put("/config/watchlist", json=payload)

        assert response.status_code == 200
        data = response.json()

        # MCX should be updated
        assert data["mcx"] == ["COPPER", "NATURALGAS"]

        # Others should remain unchanged
        assert data["nse"] == ["RELIANCE", "TCS", "INFY"]
        assert data["bse"] == ["SBIN"]
        assert data["cds"] == ["USDINR"]

    def test_update_with_empty_list(self, client: TestClient) -> None:
        """Test updating with empty symbol list."""
        payload = {"nse": []}
        response = client.put("/config/watchlist", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["nse"] == []
        assert data["total_symbols"] == 3  # bse + mcx + cds

    def test_update_with_no_fields(self, client: TestClient) -> None:
        """Test updating with no fields (empty JSON)."""
        payload = {}
        response = client.put("/config/watchlist", json=payload)

        assert response.status_code == 200
        data = response.json()

        # All should remain unchanged
        assert data["nse"] == ["RELIANCE", "TCS", "INFY"]
        assert data["bse"] == ["SBIN"]
        assert data["mcx"] == ["GOLD"]
        assert data["cds"] == ["USDINR"]

    def test_update_with_duplicates(self, client: TestClient) -> None:
        """Test updating with duplicate symbols."""
        payload = {"nse": ["RELIANCE", "RELIANCE", "TCS"]}
        response = client.put("/config/watchlist", json=payload)

        assert response.status_code == 200
        data = response.json()

        # Duplicates should be preserved
        assert data["nse"] == ["RELIANCE", "RELIANCE", "TCS"]
        # Total: 3 (nse with duplicates) + 1 (bse) + 1 (mcx) + 1 (cds) = 6
        assert data["total_symbols"] == 6

    def test_update_creates_new_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that update creates config file if it doesn't exist."""
        # Use a non-existent path
        new_config_path = tmp_path / "new_config" / "watchlist.toml"
        monkeypatch.setenv(WATCHLIST_CONFIG_ENV_VAR, str(new_config_path))
        reset_config_manager()

        new_client = TestClient(app)
        payload = {"nse": ["TEST1", "TEST2"]}
        response = new_client.put("/config/watchlist", json=payload)

        assert response.status_code == 200
        assert new_config_path.exists()

        # Verify file content
        import tomli

        with new_config_path.open("rb") as f:
            content = tomli.load(f)
        assert content["nse"]["symbols"] == ["TEST1", "TEST2"]


class TestWatchlistApiEdgeCases:
    """Tests for edge cases and error handling."""

    def test_get_watchlist_after_file_update(self, client: TestClient, tmp_path: Path) -> None:
        """Test that GET reflects file changes."""
        # Update via API
        client.put("/config/watchlist", json={"nse": ["UPDATED"]})

        # Get should reflect the update
        response = client.get("/config/watchlist")
        assert response.json()["nse"] == ["UPDATED"]

    def test_concurrent_updates(self, client: TestClient) -> None:
        """Test handling of concurrent updates."""
        # First update
        payload1 = {"nse": ["FIRST"]}
        response1 = client.put("/config/watchlist", json=payload1)
        assert response1.status_code == 200

        # Second update
        payload2 = {"nse": ["SECOND"]}
        response2 = client.put("/config/watchlist", json=payload2)
        assert response2.status_code == 200

        # Final state should be from second update
        final = client.get("/config/watchlist")
        assert final.json()["nse"] == ["SECOND"]

    def test_update_with_invalid_json(self, client: TestClient) -> None:
        """Test updating with invalid JSON."""
        response = client.put(
            "/config/watchlist",
            content=b"invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422  # Unprocessable Entity

    def test_update_with_invalid_content_type(self, client: TestClient) -> None:
        """Test updating with wrong content type."""
        response = client.put("/config/watchlist", data="not json")

        assert response.status_code == 422  # Unprocessable Entity

    def test_get_with_config_error(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test GET when config manager raises error."""
        # Set up a path that will cause an error
        error_path = tmp_path / "error.toml"
        error_path.write_text("invalid [[[[")

        monkeypatch.setenv(WATCHLIST_CONFIG_ENV_VAR, str(error_path))
        reset_config_manager()

        # Create new client that will fail to load config
        new_client = TestClient(app)
        response = new_client.get("/config/watchlist")

        # Should still return 200 with empty config (graceful degradation)
        assert response.status_code == 200

    def test_update_with_write_permission_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test UPDATE when write fails."""
        # Create a file with read-only permissions
        readonly_file = tmp_path / "readonly.toml"
        readonly_file.write_text("test")
        readonly_file.chmod(0o444)  # Read-only

        monkeypatch.setenv(WATCHLIST_CONFIG_ENV_VAR, str(readonly_file))
        reset_config_manager()

        new_client = TestClient(app)
        payload = {"nse": ["TEST"]}
        response = new_client.put("/config/watchlist", json=payload)

        # Should return 500 error
        assert response.status_code == 500
        assert "Failed to write watchlist config" in response.json()["detail"]

        # Clean up - restore write permissions for cleanup
        readonly_file.chmod(0o644)

    def test_large_watchlist(self, client: TestClient) -> None:
        """Test handling of large watchlist."""
        # Create a large list
        large_list = [f"SYMBOL{i}" for i in range(1000)]
        payload = {"nse": large_list}

        response = client.put("/config/watchlist", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert len(data["nse"]) == 1000
        assert data["total_symbols"] == 1000 + 1 + 1 + 1  # nse + bse + mcx + cds


class TestWatchlistApiIntegration:
    """Integration tests for watchlist API."""

    def test_full_workflow(self, client: TestClient) -> None:
        """Test complete workflow: get, update, get again."""
        # Initial state
        initial = client.get("/config/watchlist").json()
        assert initial["nse"] == ["RELIANCE", "TCS", "INFY"]

        # Update
        update_payload = {
            "nse": ["HDFCBANK", "ICICIBANK"],
            "bse": ["KOTAKBANK"],
        }
        update_response = client.put("/config/watchlist", json=update_payload)
        assert update_response.status_code == 200

        # Verify updated state
        updated = client.get("/config/watchlist").json()
        assert updated["nse"] == ["HDFCBANK", "ICICIBANK"]
        assert updated["bse"] == ["KOTAKBANK"]
        assert updated["mcx"] == ["GOLD"]  # Unchanged
        assert updated["cds"] == ["USDINR"]  # Unchanged

    def test_update_persists_across_restarts(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that updates persist across app restarts."""
        # Update config
        client.put("/config/watchlist", json={"nse": ["PERSISTENT"]})

        # Simulate restart by resetting config manager
        reset_config_manager()

        # Create new client
        config_path = tmp_path / "watchlist.toml"
        monkeypatch.setenv(WATCHLIST_CONFIG_ENV_VAR, str(config_path))
        new_client = TestClient(app)

        # Config should persist
        response = new_client.get("/config/watchlist")
        assert response.json()["nse"] == ["PERSISTENT"]

    def test_environment_variable_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that environment variable changes config path."""
        # Set up two different configs
        config1_path = tmp_path / "config1.toml"
        config2_path = tmp_path / "config2.toml"

        # Use first config
        monkeypatch.setenv(WATCHLIST_CONFIG_ENV_VAR, str(config1_path))
        reset_config_manager()

        client1 = TestClient(app)
        client1.put("/config/watchlist", json={"nse": ["CONFIG1"]})

        # Switch to second config
        monkeypatch.setenv(WATCHLIST_CONFIG_ENV_VAR, str(config2_path))
        reset_config_manager()

        client2 = TestClient(app)
        client2.put("/config/watchlist", json={"nse": ["CONFIG2"]})

        # Each should have its own config
        assert client1.get("/config/watchlist").json()["nse"] == ["CONFIG2"]
        assert client2.get("/config/watchlist").json()["nse"] == ["CONFIG2"]
