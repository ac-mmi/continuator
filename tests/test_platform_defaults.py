"""Platform default backend selection."""
from __future__ import annotations

from unittest import mock

from platform_defaults import default_extractor_backend


def test_default_backend_apple_silicon():
    with mock.patch("platform_defaults.sys.platform", "darwin"), mock.patch(
        "platform_defaults.platform.machine", return_value="arm64"
    ):
        assert default_extractor_backend() == "mlx"


def test_default_backend_intel_mac():
    with mock.patch("platform_defaults.sys.platform", "darwin"), mock.patch(
        "platform_defaults.platform.machine", return_value="x86_64"
    ):
        assert default_extractor_backend() == "transformers"


def test_default_backend_windows():
    with mock.patch("platform_defaults.sys.platform", "win32"), mock.patch(
        "platform_defaults.platform.machine", return_value="AMD64"
    ):
        assert default_extractor_backend() == "transformers"


def test_default_backend_linux():
    with mock.patch("platform_defaults.sys.platform", "linux"), mock.patch(
        "platform_defaults.platform.machine", return_value="x86_64"
    ):
        assert default_extractor_backend() == "transformers"
