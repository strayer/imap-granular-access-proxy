"""Tests for TCP server infrastructure."""

from twisted.internet import protocol
from twisted.mail import imap4

from imap_granular_access_proxy.server import (
    IMAPServerFactory,
    IMAPServerProtocol,
    IMAPState,
)


class TestIMAPServerProtocol:
    """Tests for IMAPServerProtocol."""

    def test_inherits_from_imap4_server(self) -> None:
        """Protocol should inherit from twisted.mail.imap4.IMAP4Server."""
        assert issubclass(IMAPServerProtocol, imap4.IMAP4Server)

    def test_protocol_instantiation(self) -> None:
        """Protocol should be instantiable."""
        proto = IMAPServerProtocol()  # type: ignore[no-untyped-call]
        assert proto is not None

    def test_initial_state_is_not_authenticated(self) -> None:
        """New protocol should start in NOT_AUTHENTICATED state."""
        proto = IMAPServerProtocol()  # type: ignore[no-untyped-call]
        assert proto.imap_state == IMAPState.NOT_AUTHENTICATED

    def test_imap_state_property_returns_enum(self) -> None:
        """imap_state property should return IMAPState enum."""
        proto = IMAPServerProtocol()  # type: ignore[no-untyped-call]
        assert isinstance(proto.imap_state, IMAPState)

    def test_selected_mailbox_initially_none(self) -> None:
        """selected_mailbox should be None when not in SELECTED state."""
        proto = IMAPServerProtocol()  # type: ignore[no-untyped-call]
        assert proto.selected_mailbox is None

    def test_check_command_allows_by_default(self) -> None:
        """check_command should return True by default (allow all)."""
        proto = IMAPServerProtocol()  # type: ignore[no-untyped-call]
        assert proto.check_command(b"A001", "LOGIN", b"user pass") is True
        assert proto.check_command(b"A002", "SELECT", b"INBOX") is True
        assert proto.check_command(b"A003", "FETCH", b"1:* FLAGS") is True


class TestIMAPState:
    """Tests for IMAPState enum."""

    def test_not_authenticated_value(self) -> None:
        """NOT_AUTHENTICATED should map to Twisted's 'unauth' state."""
        assert IMAPState.NOT_AUTHENTICATED.value == "unauth"

    def test_authenticated_value(self) -> None:
        """AUTHENTICATED should map to Twisted's 'auth' state."""
        assert IMAPState.AUTHENTICATED.value == "auth"

    def test_selected_value(self) -> None:
        """SELECTED should map to Twisted's 'select' state."""
        assert IMAPState.SELECTED.value == "select"

    def test_logout_value(self) -> None:
        """LOGOUT should map to Twisted's 'logout' state."""
        assert IMAPState.LOGOUT.value == "logout"

    def test_timeout_value(self) -> None:
        """TIMEOUT should map to Twisted's 'timeout' state."""
        assert IMAPState.TIMEOUT.value == "timeout"

    def test_state_from_twisted_string(self) -> None:
        """Should be able to create IMAPState from Twisted state strings."""
        assert IMAPState("unauth") == IMAPState.NOT_AUTHENTICATED
        assert IMAPState("auth") == IMAPState.AUTHENTICATED
        assert IMAPState("select") == IMAPState.SELECTED
        assert IMAPState("logout") == IMAPState.LOGOUT
        assert IMAPState("timeout") == IMAPState.TIMEOUT


class TestIMAPServerFactory:
    """Tests for IMAPServerFactory."""

    def test_inherits_from_factory(self) -> None:
        """Factory should inherit from twisted.internet.protocol.Factory."""
        assert issubclass(IMAPServerFactory, protocol.Factory)

    def test_factory_instantiation_defaults(self) -> None:
        """Factory should use default host and port."""
        factory = IMAPServerFactory()
        assert factory.host == "127.0.0.1"
        assert factory.port == 9993

    def test_factory_instantiation_custom(self) -> None:
        """Factory should accept custom host and port."""
        factory = IMAPServerFactory(host="0.0.0.0", port=1143)  # noqa: S104
        assert factory.host == "0.0.0.0"  # noqa: S104
        assert factory.port == 1143

    def test_factory_protocol_class(self) -> None:
        """Factory should use IMAPServerProtocol as protocol class."""
        factory = IMAPServerFactory()
        assert factory.protocol is IMAPServerProtocol

    def test_build_protocol_returns_imap_protocol(self) -> None:
        """buildProtocol should return an IMAPServerProtocol instance."""
        factory = IMAPServerFactory()

        # Create a mock address
        class MockAddress:
            host = "127.0.0.1"
            port = 12345

        proto = factory.buildProtocol(MockAddress())
        assert isinstance(proto, IMAPServerProtocol)
        assert proto.factory is factory
