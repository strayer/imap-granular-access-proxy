"""Upstream IMAP client infrastructure.

This module provides the Protocol and Factory classes for establishing
connections to upstream IMAP servers using Twisted's IMAP4 framework.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from twisted.internet import defer
from twisted.internet.protocol import ClientFactory, connectionDone
from twisted.mail import imap4
from twisted.python.failure import Failure

if TYPE_CHECKING:
    from twisted.internet.interfaces import IAddress

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpstreamConfig:
    """Configuration for an upstream IMAP server.

    Attributes:
        host: The hostname or IP address of the IMAP server.
        port: The port number (typically 993 for IMAPS, 143 for plain).
        username: The username for authentication.
        password: The password for authentication.
        use_tls: Whether to use TLS/SSL for the connection.
    """

    host: str
    port: int
    username: str
    password: str
    use_tls: bool = True


class UpstreamIMAPProtocol(imap4.IMAP4Client):
    """Protocol handler for connections to upstream IMAP servers.

    Extends Twisted's IMAP4Client to provide custom handling for the proxy.
    Each upstream connection gets its own instance of this protocol.
    """

    factory: UpstreamIMAPClientFactory
    _greeting_deferred: defer.Deferred[UpstreamIMAPProtocol] | None = None

    def connectionMade(self) -> None:
        """Called when the connection to the upstream server is established."""
        assert self.transport is not None
        peer = self.transport.getPeer()  # ty: ignore[too-many-positional-arguments]
        logger.info("Connected to upstream %s:%d", peer.host, peer.port)
        super().connectionMade()

    def connectionLost(self, reason: Failure = connectionDone) -> None:
        """Called when the upstream connection is lost."""
        assert self.transport is not None
        peer = self.transport.getPeer()  # ty: ignore[too-many-positional-arguments]
        logger.info("Disconnected from upstream %s:%d", peer.host, peer.port)
        super().connectionLost(reason)

    def serverGreeting(self, caps: dict[bytes, list[bytes] | None]) -> None:
        """Called when the server sends its initial greeting.

        Args:
            caps: The server's advertised capabilities.
        """
        logger.debug("Upstream server greeting received, capabilities: %r", caps)
        self.serverCapabilities = caps
        if self._greeting_deferred is not None:
            d, self._greeting_deferred = self._greeting_deferred, None
            d.callback(self)


class UpstreamIMAPClientFactory(ClientFactory):
    """Factory for creating connections to upstream IMAP servers.

    This factory creates UpstreamIMAPProtocol instances for connecting
    to a specific upstream IMAP server. It manages the connection lifecycle
    and provides a Deferred that fires when the connection is established.
    """

    protocol = UpstreamIMAPProtocol

    def __init__(self, config: UpstreamConfig) -> None:
        """Initialize the upstream client factory.

        Args:
            config: Configuration for the upstream server.
        """
        self.config = config
        self._connection_deferred: defer.Deferred[UpstreamIMAPProtocol] | None = None
        self._protocol: UpstreamIMAPProtocol | None = None

    def buildProtocol(self, addr: IAddress) -> UpstreamIMAPProtocol:
        """Build a protocol instance for a new connection.

        Args:
            addr: The address of the server we connected to.

        Returns:
            A new UpstreamIMAPProtocol instance.
        """
        proto = UpstreamIMAPProtocol()
        proto.factory = self
        self._protocol = proto

        # Set up the greeting deferred to fire when server sends greeting
        proto._greeting_deferred = self._connection_deferred

        # Register authenticators for the upstream server
        username_bytes = self.config.username.encode("utf-8")
        proto.registerAuthenticator(imap4.PLAINAuthenticator(username_bytes))
        proto.registerAuthenticator(imap4.LOGINAuthenticator(username_bytes))
        proto.registerAuthenticator(imap4.CramMD5ClientAuthenticator(username_bytes))

        logger.debug("Built upstream protocol for %s:%d", self.config.host, self.config.port)
        return proto

    def clientConnectionFailed(
        self, connector: object, reason: Failure
    ) -> None:
        """Called when a connection attempt fails.

        Args:
            connector: The connector that failed.
            reason: The failure reason.
        """
        logger.error(
            "Failed to connect to upstream %s:%d: %s",
            self.config.host,
            self.config.port,
            reason.getErrorMessage(),
        )
        if self._connection_deferred is not None:
            d, self._connection_deferred = self._connection_deferred, None
            d.errback(reason)

    def clientConnectionLost(
        self, connector: object, reason: Failure
    ) -> None:
        """Called when an established connection is lost.

        Args:
            connector: The connector that lost connection.
            reason: The failure reason.
        """
        logger.info(
            "Lost connection to upstream %s:%d: %s",
            self.config.host,
            self.config.port,
            reason.getErrorMessage(),
        )

    def connect(
        self, reactor: object
    ) -> defer.Deferred[UpstreamIMAPProtocol]:
        """Initiate a connection to the upstream server.

        This method creates the appropriate endpoint (TLS or plain) and
        initiates the connection. The returned Deferred fires with the
        protocol instance once the server greeting is received.

        Args:
            reactor: The Twisted reactor to use for the connection.

        Returns:
            A Deferred that fires with the connected protocol.
        """
        from twisted.internet import endpoints, ssl

        self._connection_deferred = defer.Deferred()

        endpoint = endpoints.HostnameEndpoint(
            reactor,  # type: ignore[arg-type]
            self.config.host,
            self.config.port,
        )

        if self.config.use_tls:
            context_factory = ssl.optionsForClientTLS(hostname=self.config.host)
            endpoint = endpoints.wrapClientTLS(
                context_factory,
                endpoint,  # type: ignore[arg-type]
            )

        logger.info(
            "Connecting to upstream %s:%d (TLS=%s)",
            self.config.host,
            self.config.port,
            self.config.use_tls,
        )

        # Connect and return the deferred that fires on server greeting
        endpoint.connect(self)  # type: ignore[arg-type]
        return self._connection_deferred
