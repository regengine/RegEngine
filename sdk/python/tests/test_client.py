"""
Unit tests for RegEngine Energy SDK.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import Timeout, ConnectionError

from regengine_energy import (
    EnergyCompliance,
    AuthenticationError,
    ValidationError,
    SnapshotCreationError,
    NetworkError,
    SystemStatus,
)
from regengine_energy.models import (
    SnapshotCreateRequest,
    SnapshotResponse,
    AssetInfo,
    ESPConfig,
)


class TestClientInitialization:
    """Test client initialization and authentication."""
    
    def test_client_with_api_key(self):
        """Test client initialization with API key."""
        client = EnergyCompliance(api_key="rge_test_key")
        assert client.api_key == "rge_test_key"
        assert "Bearer rge_test_key" in client.session.headers["Authorization"]
    
    def test_client_with_env_var(self, monkeypatch):
        """Test client initialization from environment variable."""
        monkeypatch.setenv("REGENGINE_API_KEY", "rge_env_key")
        client = EnergyCompliance()
        assert client.api_key == "rge_env_key"
    
    def test_client_without_api_key(self, monkeypatch):
        """Test client initialization fails without API key."""
        monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
        with pytest.raises(AuthenticationError) as exc:
            EnergyCompliance()
        assert "API key required" in str(exc.value)
    
    def test_custom_base_url(self):
        """Test client with custom base URL."""
        client = EnergyCompliance(
            api_key="rge_test",
            base_url="http://localhost:8000/v1/energy"
        )
        assert client.base_url == "http://localhost:8000/v1/energy"


class TestPydanticModels:
    """Test Pydantic model validation."""
    
    def test_valid_snapshot_request(self):
        """Test creating valid snapshot request."""
        request = SnapshotCreateRequest(
            substation_id="ALPHA-001",
            facility_name="Alpha Substation",
            system_status=SystemStatus.NOMINAL,
            assets=[
                AssetInfo(
                    id="T1",
                    type="TRANSFORMER",
                    firmware_version="2.4.1",
                    last_verified="2026-01-26T15:00:00Z"
                )
            ],
            esp_config=ESPConfig(
                firewall_version="2.4.1",
                ids_enabled=True,
                patch_level="current"
            )
        )
        assert request.substation_id == "ALPHA-001"
        assert len(request.assets) == 1
    
    def test_empty_substation_id_fails(self):
        """Test empty substation ID fails validation."""
        with pytest.raises(ValueError):
            SnapshotCreateRequest(
                substation_id="",
                facility_name="Test",
                system_status=SystemStatus.NOMINAL,
                assets=[
                    AssetInfo(
                        id="T1",
                        type="TRANSFORMER",
                        last_verified="2026-01-26T15:00:00Z"
                    )
                ],
                esp_config=ESPConfig(
                    firewall_version="1.0",
                    ids_enabled=True,
                    patch_level="current"
                )
            )
    
    def test_empty_assets_fails(self):
        """Test empty assets list fails validation."""
        with pytest.raises(ValueError) as exc:
            SnapshotCreateRequest(
                substation_id="ALPHA-001",
                facility_name="Test",
                system_status=SystemStatus.NOMINAL,
                assets=[],
                esp_config=ESPConfig(
                    firewall_version="1.0",
                    ids_enabled=True,
                    patch_level="current"
                )
            )
        # Pydantic V2 provides its own validation message for min_length
        assert "at least 1 item" in str(exc.value).lower()


class TestSnapshotOperations:
    """Test snapshot creation and retrieval."""
    
    @patch('regengine_energy.client.requests.Session')
    def test_create_snapshot_success(self, mock_session_class):
        """Test successful snapshot creation."""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "snapshot_id": "snap_123",
            "snapshot_time": "2026-01-26T15:00:00Z",
            "system_status": "NOMINAL",
            "content_hash": "abc123...",
            "asset_summary": {"total": 1, "verified": 1},
        }
        
        mock_session = Mock()
        mock_session.request.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        client = EnergyCompliance(api_key="rge_test")
        client.session = mock_session
        
        snapshot = client.snapshots.create(
            substation_id="ALPHA-001",
            facility_name="Alpha Substation",
            system_status="NOMINAL",
            assets=[{
                "id": "T1",
                "type": "TRANSFORMER",
                "last_verified": "2026-01-26T15:00:00Z"
            }],
            esp_config={
                "firewall_version": "2.4.1",
                "ids_enabled": True,
                "patch_level": "current"
            }
        )
        
        assert snapshot.snapshot_id == "snap_123"
        assert snapshot.system_status == "NOMINAL"
        assert mock_session.request.called
    
    @patch('regengine_energy.client.requests.Session')
    def test_create_snapshot_validation_error(self, mock_session_class):
        """Test snapshot creation with validation error."""
        mock_response = Mock()
        mock_response.status_code = 422
        mock_response.content = b'{"detail": "Invalid data"}'
        mock_response.json.return_value = {"detail": "Invalid data"}
        
        mock_session = Mock()
        mock_session.request.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        client = EnergyCompliance(api_key="rge_test")
        client.session = mock_session
        
        with pytest.raises(ValidationError) as exc:
            client.snapshots.create(
                substation_id="ALPHA-001",
                facility_name="Alpha Substation",
                system_status="NOMINAL",
                assets=[{
                    "id": "T1",
                    "type": "TRANSFORMER",
                    "last_verified": "2026-01-26T15:00:00Z"
                }],
                esp_config={
                    "firewall_version": "2.4.1",
                    "ids_enabled": True,
                    "patch_level": "current"
                }
            )
        assert "Invalid data" in str(exc.value)


class TestErrorHandling:
    """Test error handling and retry logic."""
    
    @patch('regengine_energy.client.requests.Session')
    def test_authentication_error_401(self, mock_session_class):
        """Test 401 raises AuthenticationError."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.content = b''
        
        mock_session = Mock()
        mock_session.request.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        client = EnergyCompliance(api_key="rge_invalid")
        client.session = mock_session
        
        with pytest.raises(AuthenticationError):
            client._request("GET", "/snapshots")
    
    @patch('regengine_energy.client.requests.Session')
    def test_network_timeout(self, mock_session_class):
        """Test network timeout raises NetworkError."""
        mock_session = Mock()
        mock_session.request.side_effect = Timeout()
        mock_session_class.return_value = mock_session
        
        client = EnergyCompliance(api_key="rge_test")
        client.session = mock_session
        
        with pytest.raises(NetworkError) as exc:
            client._request("GET", "/snapshots")
        assert "timeout" in str(exc.value).lower()


class TestVerificationOperations:
    """Test chain verification operations."""
    
    @patch('regengine_energy.client.requests.Session')
    def test_verify_latest_success(self, mock_session_class):
        """Test successful latest snapshot verification."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "verified": True,
            "snapshot_id": "snap_123",
            "content_hash_valid": True,
            "chain_intact": True,
        }
        
        mock_session = Mock()
        mock_session.request.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        client = EnergyCompliance(api_key="rge_test")
        client.session = mock_session
        
        result = client.verification.verify_latest("ALPHA-001")
        
        assert result.verified is True
        assert result.chain_intact is True
        assert mock_session.request.called
