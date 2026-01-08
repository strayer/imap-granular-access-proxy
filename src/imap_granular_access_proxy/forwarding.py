"""Command forwarding pipeline for the IMAP proxy.

This module provides the infrastructure for forwarding IMAP commands
from clients to upstream servers and routing responses back. It handles
tag rewriting to avoid collisions and maintains proper command tracking.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


class ResponseSender(Protocol):
    """Protocol for objects that can send IMAP responses.

    This is used to decouple the forwarding pipeline from the specific
    protocol implementation.
    """

    def sendLine(self, line: bytes) -> None:
        """Send a line of data."""
        ...


class CommandSender(Protocol):
    """Protocol for objects that can send IMAP commands.

    This is used to decouple the forwarding pipeline from the specific
    protocol implementation.
    """

    def sendLine(self, line: bytes) -> None:
        """Send a line of data."""
        ...


@dataclass
class ForwardedCommand:
    """Represents a command being forwarded from client to upstream.

    Attributes:
        client_tag: The original tag from the client.
        upstream_tag: The tag used when forwarding to upstream.
        command: The IMAP command name (uppercase).
        args: The command arguments, if any.
        timestamp: When the command was forwarded (monotonic time).
    """

    client_tag: bytes
    upstream_tag: bytes
    command: str
    args: bytes | None
    timestamp: float = field(default_factory=time.monotonic)


class ForwardingPipeline:
    """Manages the forwarding of IMAP commands and response routing.

    This class sits between the client-facing protocol and the upstream
    protocol, handling:
    - Tag rewriting to avoid collisions
    - Tracking in-flight commands
    - Routing tagged responses back to the correct client tag
    - Passing through untagged responses

    The pipeline uses a simple tag generation scheme (P0001, P0002, etc.)
    to avoid any collision with client-chosen tags.
    """

    def __init__(self) -> None:
        """Initialize an empty forwarding pipeline."""
        # Maps upstream_tag -> ForwardedCommand
        self._in_flight: dict[bytes, ForwardedCommand] = {}
        # Maps client_tag -> upstream_tag for reverse lookup
        self._client_to_upstream: dict[bytes, bytes] = {}
        self._tag_counter: int = 0

    def generate_upstream_tag(self) -> bytes:
        """Generate a unique tag for the upstream server.

        Returns:
            A unique tag in the format "P0001", "P0002", etc.
        """
        self._tag_counter += 1
        return f"P{self._tag_counter:04d}".encode("ascii")

    def forward_command(
        self,
        client_tag: bytes,
        command: str,
        args: bytes | None,
        upstream: CommandSender,
    ) -> ForwardedCommand:
        """Forward a command from the client to the upstream server.

        This method rewrites the command tag and sends it to the upstream
        server. The original client tag is tracked so responses can be
        routed back correctly.

        Args:
            client_tag: The tag used by the client.
            command: The IMAP command name (uppercase).
            args: The command arguments, or None.
            upstream: The upstream protocol to send to.

        Returns:
            The ForwardedCommand tracking object.

        Raises:
            ValueError: If a command with this client tag is already in flight.
        """
        if client_tag in self._client_to_upstream:
            raise ValueError(f"Command with client tag {client_tag!r} already in flight")

        upstream_tag = self.generate_upstream_tag()
        cmd = ForwardedCommand(
            client_tag=client_tag,
            upstream_tag=upstream_tag,
            command=command,
            args=args,
        )

        self._in_flight[upstream_tag] = cmd
        self._client_to_upstream[client_tag] = upstream_tag

        # Build and send the command line
        if args:
            line = upstream_tag + b" " + command.encode("ascii") + b" " + args
        else:
            line = upstream_tag + b" " + command.encode("ascii")

        logger.debug(
            "Forwarding command: client=%r upstream=%r cmd=%s",
            client_tag,
            upstream_tag,
            command,
        )
        upstream.sendLine(line)

        return cmd

    def route_response(
        self,
        line: bytes,
        client: ResponseSender,
    ) -> bool:
        """Route a response from upstream back to the client.

        This method examines the response line and:
        - For tagged responses (OK, NO, BAD): Rewrites the tag back to
          the original client tag and removes the command from tracking.
        - For untagged responses (*): Passes through unchanged.
        - For continuation requests (+): Passes through unchanged.

        Args:
            line: The response line from the upstream server.
            client: The client protocol to send to.

        Returns:
            True if this was a tagged response that completed a command,
            False otherwise.
        """
        if not line:
            return False

        # Check for tagged response
        if not line.startswith(b"*") and not line.startswith(b"+"):
            # This is a tagged response - find the tag
            space_idx = line.find(b" ")
            if space_idx > 0:
                upstream_tag = line[:space_idx]
                rest = line[space_idx + 1 :]

                cmd = self._in_flight.get(upstream_tag)
                if cmd:
                    # Rewrite the tag and send to client
                    rewritten = cmd.client_tag + b" " + rest
                    client.sendLine(rewritten)

                    # Clean up tracking
                    del self._in_flight[upstream_tag]
                    del self._client_to_upstream[cmd.client_tag]

                    elapsed = time.monotonic() - cmd.timestamp
                    logger.debug(
                        "Command completed: client=%r upstream=%r cmd=%s elapsed=%.3fs",
                        cmd.client_tag,
                        upstream_tag,
                        cmd.command,
                        elapsed,
                    )
                    return True

        # Untagged or continuation - pass through
        client.sendLine(line)
        return False

    def get_forwarded_by_client_tag(
        self, client_tag: bytes
    ) -> ForwardedCommand | None:
        """Get a forwarded command by its original client tag.

        Args:
            client_tag: The original client tag.

        Returns:
            The ForwardedCommand if found, None otherwise.
        """
        upstream_tag = self._client_to_upstream.get(client_tag)
        if upstream_tag:
            return self._in_flight.get(upstream_tag)
        return None

    def get_forwarded_by_upstream_tag(
        self, upstream_tag: bytes
    ) -> ForwardedCommand | None:
        """Get a forwarded command by its upstream tag.

        Args:
            upstream_tag: The upstream tag.

        Returns:
            The ForwardedCommand if found, None otherwise.
        """
        return self._in_flight.get(upstream_tag)

    @property
    def in_flight_count(self) -> int:
        """Return the number of commands currently in flight."""
        return len(self._in_flight)

    @property
    def in_flight_client_tags(self) -> frozenset[bytes]:
        """Return all client tags with commands currently in flight."""
        return frozenset(self._client_to_upstream.keys())

    def clear_all(self) -> int:
        """Clear all in-flight commands (e.g., on connection close).

        Returns:
            The number of commands that were cleared.
        """
        count = len(self._in_flight)
        self._in_flight.clear()
        self._client_to_upstream.clear()
        if count > 0:
            logger.debug("Cleared %d in-flight forwarded commands", count)
        return count

    def cancel_by_client_tag(self, client_tag: bytes) -> ForwardedCommand | None:
        """Cancel a forwarded command by its client tag.

        This removes the command from tracking without completing it.
        Useful for handling timeouts or client disconnections.

        Args:
            client_tag: The original client tag.

        Returns:
            The cancelled ForwardedCommand, or None if not found.
        """
        upstream_tag = self._client_to_upstream.pop(client_tag, None)
        if upstream_tag:
            cmd = self._in_flight.pop(upstream_tag, None)
            if cmd:
                logger.debug(
                    "Cancelled command: client=%r upstream=%r cmd=%s",
                    client_tag,
                    upstream_tag,
                    cmd.command,
                )
            return cmd
        return None
