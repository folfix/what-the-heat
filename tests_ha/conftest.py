"""Fixtures for tests that run against a real Home Assistant core.

These need pytest-homeassistant-custom-component, unlike the tests in tests/.
"""

import sys

import pytest

if sys.platform == "win32":
    # On Windows the asyncio event loop needs a socket pair, which the plugin's socket
    # guard forbids. The tests make no network calls.
    import pytest_socket

    pytest_socket.disable_socket = lambda *_args, **_kwargs: None
    pytest_socket.socket_allow_hosts = lambda *_args, **_kwargs: None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from this repository."""
    return


@pytest.fixture
def mock_recorder_before_hass(request: pytest.FixtureRequest) -> None:
    """Prepare the recorder's database before Home Assistant starts, for tests that use it.

    Home Assistant starts early here, for the fixture above, and the database must exist first.
    """
    if "recorder_mock" in request.fixturenames:
        request.getfixturevalue("recorder_db_url")
