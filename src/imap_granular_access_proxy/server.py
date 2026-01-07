"""TCP server infrastructure for the IMAP proxy.

This module provides the Protocol and Factory classes for accepting
client connections on a configurable port using Twisted's IMAP4 framework.
"""

from __future__ import annotations

import logging
from typing import Any

from twisted.internet.protocol import Factory
from twisted.mail import imap4
from twisted.python.failure import Failure

logger = logging.getLogger(__name__)


class IMAPServerProtocol(imap4.IMAP4Server):
    """Protocol handler for incoming IMAP client connections.

    Extends Twisted's IMAP4Server to provide custom handling for the proxy.
    Each connected client gets its own instance of this protocol.
    """

    factory: IMAPServerFactory

    def connectionMade(self) -> None:
        """Called when a client connects."""
        peer = self.transport.getPeer()  # type: ignore[union-attr,misc]
        logger.info("Client connected from %s:%d", peer.host, peer.port)
        super().connectionMade()  # type: ignore[no-untyped-call]

    def connectionLost(self, reason: Failure) -> None:  # type: ignore[override]
        """Called when the client connection is lost."""
        peer = self.transport.getPeer()  # type: ignore[union-attr,misc]
        logger.info("Client disconnected from %s:%d", peer.host, peer.port)
        super().connectionLost(reason)  # type: ignore[no-untyped-call]

    def lineReceived(self, line: bytes) -> None:
        """Called when a line is received from the client."""
        logger.debug("Received: %r", line)
        super().lineReceived(line)  # type: ignore[no-untyped-call]

    def sendLine(self, line: bytes) -> None:
        """Called when sending a line to the client."""
        logger.debug("Sending: %r", line)
        super().sendLine(line)  # type: ignore[no-untyped-call]


class IMAPServerFactory(Factory):
    """Factory for creating IMAPServerProtocol instances.

    This factory creates a new protocol instance for each incoming connection.
    """

    protocol = IMAPServerProtocol

    def __init__(self, host: str = "127.0.0.1", port: int = 9993) -> None:
        """Initialize the IMAP server factory.

        Args:
            host: The host/interface to bind to.
            port: The port to listen on.
        """
        self.host = host
        self.port = port

    def buildProtocol(self, addr: Any) -> IMAPServerProtocol:
        """Build a protocol instance for a new connection.

        Args:
            addr: The address of the connecting client.

        Returns:
            A new IMAPServerProtocol instance.
        """
        proto = IMAPServerProtocol()  # type: ignore[no-untyped-call]
        proto.factory = self
        return proto
