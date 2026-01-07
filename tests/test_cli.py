"""Tests for CLI module."""

from imap_granular_access_proxy.cli import main


def test_main_returns_zero(capsys, monkeypatch):
    """Test that main() returns 0 and prints startup message."""
    monkeypatch.setattr("sys.argv", ["imap-proxy"])
    result = main()
    assert result == 0

    captured = capsys.readouterr()
    assert "IMAP Granular Access Proxy" in captured.out
