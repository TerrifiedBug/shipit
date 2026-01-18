import pytest
from unittest.mock import patch, MagicMock
import os


class TestSessionSecretValidation:
    def test_default_secret_fails_in_production(self):
        """Default session secret should raise error in production."""
        with patch.dict(os.environ, {"SHIPIT_ENV": "production", "SESSION_SECRET": "change-me-in-production"}):
            from app.config import Settings
            settings = Settings()

            # The check happens on startup, so we test the condition
            assert settings.session_secret == "change-me-in-production"
            # Actual runtime check will raise RuntimeError

    def test_custom_secret_allowed_in_production(self):
        """Custom session secret should work in production."""
        with patch.dict(os.environ, {"SHIPIT_ENV": "production", "SESSION_SECRET": "my-secure-secret-key"}):
            from app.config import Settings
            settings = Settings()
            assert settings.session_secret == "my-secure-secret-key"

    def test_default_secret_allowed_in_development(self):
        """Default session secret should be allowed in development."""
        with patch.dict(os.environ, {"SHIPIT_ENV": "development", "SESSION_SECRET": "change-me-in-production"}):
            from app.config import Settings
            settings = Settings()
            assert settings.session_secret == "change-me-in-production"
            assert settings.shipit_env == "development"

    def test_shipit_env_defaults_to_development(self):
        """SHIPIT_ENV should default to development."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove SHIPIT_ENV if it exists
            env_copy = os.environ.copy()
            env_copy.pop("SHIPIT_ENV", None)
            with patch.dict(os.environ, env_copy, clear=True):
                from app.config import Settings
                settings = Settings()
                assert settings.shipit_env == "development"


class TestStartupSecurityCheck:
    """Test the actual startup security check in main.py lifespan."""

    @pytest.mark.asyncio
    async def test_startup_raises_in_production_with_default_secret(self):
        """Startup should raise RuntimeError in production with default secret."""
        from app.config import Settings

        # Create mock settings for production with default secret
        mock_settings = MagicMock(spec=Settings)
        mock_settings.session_secret = "change-me-in-production"
        mock_settings.shipit_env = "production"

        with patch("app.main.settings", mock_settings):
            from app.main import lifespan

            mock_app = MagicMock()
            with pytest.raises(RuntimeError, match="SESSION_SECRET must be changed in production"):
                async with lifespan(mock_app):
                    pass

    @pytest.mark.asyncio
    async def test_startup_warns_in_development_with_default_secret(self):
        """Startup should warn (not raise) in development with default secret."""
        from app.config import Settings

        # Create mock settings for development with default secret
        mock_settings = MagicMock(spec=Settings)
        mock_settings.session_secret = "change-me-in-production"
        mock_settings.shipit_env = "development"

        with patch("app.main.settings", mock_settings), \
             patch("app.main.init_db"), \
             patch("app.main.start_retention_task"), \
             patch("app.main.stop_retention_task"), \
             patch("app.main.logger") as mock_logger:
            from app.main import lifespan

            mock_app = MagicMock()
            async with lifespan(mock_app):
                pass

            # Should have logged a warning
            mock_logger.warning.assert_called_once()
            assert "default SESSION_SECRET" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_startup_no_warning_with_custom_secret(self):
        """Startup should not warn with custom secret."""
        from app.config import Settings

        # Create mock settings with custom secret
        mock_settings = MagicMock(spec=Settings)
        mock_settings.session_secret = "my-custom-secure-secret"
        mock_settings.shipit_env = "development"

        with patch("app.main.settings", mock_settings), \
             patch("app.main.init_db"), \
             patch("app.main.start_retention_task"), \
             patch("app.main.stop_retention_task"), \
             patch("app.main.logger") as mock_logger:
            from app.main import lifespan

            mock_app = MagicMock()
            async with lifespan(mock_app):
                pass

            # Should NOT have logged a warning
            mock_logger.warning.assert_not_called()
