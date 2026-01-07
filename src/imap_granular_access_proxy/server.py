"""TCP server infrastructure for the IMAP proxy.

This module provides the Protocol and Factory classes for accepting
client connections on a configurable port using Twisted's IMAP4 framework.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from twisted.internet.protocol import Factory, connectionDone
from twisted.mail import imap4
from twisted.python.failure import Failure

logger = logging.getLogger(__name__)


class IMAPState(Enum):
    """IMAP connection states as defined in RFC 3501.

    The IMAP protocol defines four states:
    - NOT_AUTHENTICATED: Initial state after connection
    - AUTHENTICATED: After successful LOGIN/AUTHENTICATE
    - SELECTED: After successful SELECT/EXAMINE of a mailbox
    - LOGOUT: Connection is being terminated
    - TIMEOUT: Connection timed out (Twisted-specific)
    """

    NOT_AUTHENTICATED = "unauth"
    AUTHENTICATED = "auth"
    SELECTED = "select"
    LOGOUT = "logout"
    TIMEOUT = "timeout"


class IMAPServerProtocol(imap4.IMAP4Server):
    """Protocol handler for incoming IMAP client connections.

    Extends Twisted's IMAP4Server to provide custom handling for the proxy.
    Each connected client gets its own instance of this protocol.
    """

    factory: IMAPServerFactory
    _selected_mailbox: str | None = None

    @property
    def imap_state(self) -> IMAPState:
        """Get the current IMAP connection state as a typed enum.

        Returns:
            The current IMAPState based on Twisted's internal state string.
        """
        return IMAPState(self.state)

    @property
    def selected_mailbox(self) -> str | None:
        """Get the currently selected mailbox name, if any.

        Returns:
            The mailbox name if in SELECTED state, None otherwise.
        """
        return self._selected_mailbox

    def connectionMade(self) -> None:
        """Called when a client connects."""
        assert self.transport is not None
        peer = self.transport.getPeer()  # ty: ignore[too-many-positional-arguments]
        logger.info("Client connected from %s:%d", peer.host, peer.port)
        super().connectionMade()

    def connectionLost(self, reason: Failure = connectionDone) -> None:
        """Called when the client connection is lost."""
        assert self.transport is not None
        peer = self.transport.getPeer()  # ty: ignore[too-many-positional-arguments]
        logger.info("Client disconnected from %s:%d", peer.host, peer.port)
        super().connectionLost(reason)

    def lineReceived(self, line: bytes) -> None:
        """Called when a line is received from the client."""
        logger.debug("Received: %r", line)
        super().lineReceived(line)

    def sendLine(self, line: bytes) -> None:
        """Called when sending a line to the client."""
        logger.debug("Sending: %r", line)
        super().sendLine(line)

    def dispatchCommand(
        self, tag: bytes, cmd: bytes, rest: bytes | None, uid: int | None = None
    ) -> None:
        """Dispatch an IMAP command after parsing.

        This is the interception point for ACL checks. The command has been
        parsed by Twisted and we can inspect/block it before execution.

        Args:
            tag: The command tag (e.g., b"A001")
            cmd: The command name in uppercase (e.g., b"SELECT")
            rest: The remaining arguments, or None
            uid: UID prefix flag for UID commands
        """
        cmd_str = cmd.decode("ascii", errors="replace")
        logger.debug(
            "Command: tag=%r cmd=%s args=%r state=%s",
            tag,
            cmd_str,
            rest,
            self.imap_state.name,
        )

        # Hook point for ACL checks - subclasses or future code can
        # override check_command() to implement access control
        if not self.check_command(tag, cmd_str, rest):
            return  # Command was rejected

        super().dispatchCommand(tag, cmd, rest, uid)

    def check_command(self, tag: bytes, cmd: str, args: bytes | None) -> bool:
        """Check if a command should be allowed.

        Override this method to implement ACL checks. Return False to
        reject the command (and send an appropriate error response).

        Args:
            tag: The command tag
            cmd: The command name in uppercase
            args: The command arguments, or None

        Returns:
            True to allow the command, False to reject it.
        """
        # Default: allow all commands (ACL logic will be added later)
        return True


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
        proto = IMAPServerProtocol()
        proto.factory = self
        return proto
