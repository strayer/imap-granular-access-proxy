"""Tests for TCP server infrastructure."""

from twisted.internet import protocol
from twisted.mail import imap4

from imap_granular_access_proxy.server import IMAPServerFactory, IMAPServerProtocol


class TestIMAPServerProtocol:
    """Tests for IMAPServerProtocol."""

    def test_inherits_from_imap4_server(self) -> None:
        """Protocol should inherit from twisted.mail.imap4.IMAP4Server."""
        assert issubclass(IMAPServerProtocol, imap4.IMAP4Server)

    def test_protocol_instantiation(self) -> None:
        """Protocol should be instantiable."""
        proto = IMAPServerProtocol()  # type: ignore[no-untyped-call]
        assert proto is not None


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
