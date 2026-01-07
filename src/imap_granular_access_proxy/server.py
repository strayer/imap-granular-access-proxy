"""TCP server infrastructure for the IMAP proxy.

This module provides the Protocol and Factory classes for accepting
client connections on a configurable port using Twisted's IMAP4 framework.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from twisted.internet.protocol import Factory, connectionDone
from twisted.mail import imap4
from twisted.python.failure import Failure

logger = logging.getLogger(__name__)


@dataclass
class PendingCommand:
    """Represents an in-flight IMAP command awaiting a response.

    Attributes:
        client_tag: The tag used by the client for this command.
        command: The IMAP command name (uppercase).
        args: The command arguments, if any.
        timestamp: When the command was received (monotonic time).
        upstream_tag: The tag used when forwarding to upstream (may differ).
    """

    client_tag: bytes
    command: str
    args: bytes | None
    timestamp: float = field(default_factory=time.monotonic)
    upstream_tag: bytes | None = None


class CommandTagTracker:
    """Tracks in-flight IMAP commands and routes responses.

    IMAP uses tags to correlate commands with responses. When a client
    sends "A001 SELECT INBOX", the server responds with "A001 OK SELECT completed".
    This tracker maintains the mapping between tags and pending commands.

    In a proxy scenario, we may need to:
    - Rewrite tags to avoid collisions with upstream
    - Track which client command maps to which upstream command
    - Handle timeouts for commands that never receive responses
    """

    def __init__(self) -> None:
        """Initialize an empty command tracker."""
        self._pending: dict[bytes, PendingCommand] = {}
        self._tag_counter: int = 0

    def register_command(
        self, tag: bytes, command: str, args: bytes | None
    ) -> PendingCommand:
        """Register a new command as pending.

        Args:
            tag: The client's command tag.
            command: The IMAP command name.
            args: The command arguments.

        Returns:
            The created PendingCommand instance.

        Raises:
            ValueError: If a command with this tag is already pending.
        """
        if tag in self._pending:
            raise ValueError(f"Duplicate command tag: {tag!r}")

        cmd = PendingCommand(client_tag=tag, command=command, args=args)
        self._pending[tag] = cmd
        logger.debug("Registered pending command: tag=%r cmd=%s", tag, command)
        return cmd

    def complete_command(self, tag: bytes) -> PendingCommand | None:
        """Mark a command as complete and remove it from tracking.

        Args:
            tag: The tag of the command to complete.

        Returns:
            The completed PendingCommand, or None if not found.
        """
        cmd = self._pending.pop(tag, None)
        if cmd:
            elapsed = time.monotonic() - cmd.timestamp
            logger.debug(
                "Completed command: tag=%r cmd=%s elapsed=%.3fs",
                tag,
                cmd.command,
                elapsed,
            )
        return cmd

    def get_pending(self, tag: bytes) -> PendingCommand | None:
        """Get a pending command by its tag.

        Args:
            tag: The command tag to look up.

        Returns:
            The PendingCommand if found, None otherwise.
        """
        return self._pending.get(tag)

    def has_pending(self, tag: bytes) -> bool:
        """Check if a tag has a pending command.

        Args:
            tag: The command tag to check.

        Returns:
            True if the tag has a pending command.
        """
        return tag in self._pending

    @property
    def pending_count(self) -> int:
        """Return the number of pending commands."""
        return len(self._pending)

    @property
    def pending_tags(self) -> frozenset[bytes]:
        """Return all currently pending tags."""
        return frozenset(self._pending.keys())

    def generate_upstream_tag(self) -> bytes:
        """Generate a unique tag for forwarding to upstream.

        This ensures we don't have tag collisions between the client's
        tags and our upstream tags.

        Returns:
            A unique tag in the format "P0001", "P0002", etc.
        """
        self._tag_counter += 1
        return f"P{self._tag_counter:04d}".encode("ascii")

    def clear_all(self) -> int:
        """Clear all pending commands (e.g., on connection close).

        Returns:
            The number of commands that were cleared.
        """
        count = len(self._pending)
        self._pending.clear()
        if count > 0:
            logger.debug("Cleared %d pending commands", count)
        return count


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
    _tag_tracker: CommandTagTracker

    def __init__(self) -> None:
        """Initialize the protocol with a command tag tracker."""
        super().__init__()
        self._tag_tracker = CommandTagTracker()

    @property
    def tag_tracker(self) -> CommandTagTracker:
        """Get the command tag tracker for this connection."""
        return self._tag_tracker

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
        # Clear any pending commands that won't receive responses
        cleared = self._tag_tracker.clear_all()
        if cleared > 0:
            logger.warning("Connection lost with %d pending commands", cleared)
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

        # Track the command for response routing
        try:
            self._tag_tracker.register_command(tag, cmd_str, rest)
        except ValueError:
            # Duplicate tag - reject with BAD response
            self.sendBadResponse(tag, b"Command tag already in use")
            return

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

    def sendPositiveResponse(
        self, tag: bytes | None = None, message: bytes = b""
    ) -> None:
        """Send an OK response and complete the command tracking."""
        if tag is not None:
            self._tag_tracker.complete_command(tag)
        super().sendPositiveResponse(tag, message)

    def sendNegativeResponse(
        self, tag: bytes | None = None, message: bytes = b""
    ) -> None:
        """Send a NO response and complete the command tracking."""
        if tag is not None:
            self._tag_tracker.complete_command(tag)
        super().sendNegativeResponse(tag, message)

    def sendBadResponse(
        self, tag: bytes | None = None, message: bytes = b""
    ) -> None:
        """Send a BAD response and complete the command tracking."""
        if tag is not None:
            self._tag_tracker.complete_command(tag)
        super().sendBadResponse(tag, message)


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
