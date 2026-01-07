"""Tests for TCP server infrastructure."""

import pytest
from twisted.internet import protocol
from twisted.mail import imap4

from imap_granular_access_proxy.server import (
    CommandTagTracker,
    IMAPServerFactory,
    IMAPServerProtocol,
    IMAPState,
    PendingCommand,
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


class TestPendingCommand:
    """Tests for PendingCommand dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """PendingCommand should be creatable with required fields."""
        cmd = PendingCommand(client_tag=b"A001", command="SELECT", args=b"INBOX")
        assert cmd.client_tag == b"A001"
        assert cmd.command == "SELECT"
        assert cmd.args == b"INBOX"

    def test_creation_with_none_args(self) -> None:
        """PendingCommand should accept None for args."""
        cmd = PendingCommand(client_tag=b"A002", command="NOOP", args=None)
        assert cmd.args is None

    def test_timestamp_is_set_automatically(self) -> None:
        """PendingCommand should have timestamp set automatically."""
        cmd = PendingCommand(client_tag=b"A001", command="SELECT", args=b"INBOX")
        assert cmd.timestamp > 0

    def test_upstream_tag_defaults_to_none(self) -> None:
        """upstream_tag should default to None."""
        cmd = PendingCommand(client_tag=b"A001", command="SELECT", args=b"INBOX")
        assert cmd.upstream_tag is None

    def test_upstream_tag_can_be_set(self) -> None:
        """upstream_tag should be settable."""
        cmd = PendingCommand(
            client_tag=b"A001", command="SELECT", args=b"INBOX", upstream_tag=b"P0001"
        )
        assert cmd.upstream_tag == b"P0001"


class TestCommandTagTracker:
    """Tests for CommandTagTracker."""

    def test_initial_state(self) -> None:
        """New tracker should be empty."""
        tracker = CommandTagTracker()
        assert tracker.pending_count == 0
        assert tracker.pending_tags == frozenset()

    def test_register_command(self) -> None:
        """Should register a command and return PendingCommand."""
        tracker = CommandTagTracker()
        cmd = tracker.register_command(b"A001", "SELECT", b"INBOX")

        assert isinstance(cmd, PendingCommand)
        assert cmd.client_tag == b"A001"
        assert cmd.command == "SELECT"
        assert cmd.args == b"INBOX"
        assert tracker.pending_count == 1

    def test_register_multiple_commands(self) -> None:
        """Should track multiple commands with different tags."""
        tracker = CommandTagTracker()
        tracker.register_command(b"A001", "SELECT", b"INBOX")
        tracker.register_command(b"A002", "FETCH", b"1:* FLAGS")
        tracker.register_command(b"A003", "NOOP", None)

        assert tracker.pending_count == 3
        assert tracker.pending_tags == frozenset({b"A001", b"A002", b"A003"})

    def test_register_duplicate_tag_raises(self) -> None:
        """Should raise ValueError for duplicate tag."""
        tracker = CommandTagTracker()
        tracker.register_command(b"A001", "SELECT", b"INBOX")

        with pytest.raises(ValueError, match="Duplicate command tag"):
            tracker.register_command(b"A001", "NOOP", None)

    def test_has_pending(self) -> None:
        """has_pending should return correct boolean."""
        tracker = CommandTagTracker()
        assert tracker.has_pending(b"A001") is False

        tracker.register_command(b"A001", "SELECT", b"INBOX")
        assert tracker.has_pending(b"A001") is True
        assert tracker.has_pending(b"A002") is False

    def test_get_pending(self) -> None:
        """get_pending should return command or None."""
        tracker = CommandTagTracker()
        assert tracker.get_pending(b"A001") is None

        tracker.register_command(b"A001", "SELECT", b"INBOX")
        cmd = tracker.get_pending(b"A001")
        assert cmd is not None
        assert cmd.command == "SELECT"

    def test_complete_command(self) -> None:
        """complete_command should remove and return the command."""
        tracker = CommandTagTracker()
        tracker.register_command(b"A001", "SELECT", b"INBOX")

        cmd = tracker.complete_command(b"A001")
        assert cmd is not None
        assert cmd.client_tag == b"A001"
        assert tracker.pending_count == 0
        assert tracker.has_pending(b"A001") is False

    def test_complete_nonexistent_returns_none(self) -> None:
        """complete_command should return None for unknown tag."""
        tracker = CommandTagTracker()
        cmd = tracker.complete_command(b"A999")
        assert cmd is None

    def test_generate_upstream_tag(self) -> None:
        """generate_upstream_tag should produce unique tags."""
        tracker = CommandTagTracker()

        tag1 = tracker.generate_upstream_tag()
        tag2 = tracker.generate_upstream_tag()
        tag3 = tracker.generate_upstream_tag()

        assert tag1 == b"P0001"
        assert tag2 == b"P0002"
        assert tag3 == b"P0003"
        # All tags should be unique
        assert len({tag1, tag2, tag3}) == 3

    def test_clear_all(self) -> None:
        """clear_all should remove all pending commands."""
        tracker = CommandTagTracker()
        tracker.register_command(b"A001", "SELECT", b"INBOX")
        tracker.register_command(b"A002", "FETCH", b"1:* FLAGS")

        count = tracker.clear_all()
        assert count == 2
        assert tracker.pending_count == 0

    def test_clear_all_empty(self) -> None:
        """clear_all on empty tracker should return 0."""
        tracker = CommandTagTracker()
        count = tracker.clear_all()
        assert count == 0


class TestIMAPServerProtocolTagTracking:
    """Tests for tag tracking integration in IMAPServerProtocol."""

    def test_protocol_has_tag_tracker(self) -> None:
        """Protocol should have a tag_tracker property."""
        proto = IMAPServerProtocol()  # type: ignore[no-untyped-call]
        assert isinstance(proto.tag_tracker, CommandTagTracker)

    def test_each_protocol_has_own_tracker(self) -> None:
        """Each protocol instance should have its own tracker."""
        proto1 = IMAPServerProtocol()  # type: ignore[no-untyped-call]
        proto2 = IMAPServerProtocol()  # type: ignore[no-untyped-call]

        proto1.tag_tracker.register_command(b"A001", "SELECT", b"INBOX")

        assert proto1.tag_tracker.pending_count == 1
        assert proto2.tag_tracker.pending_count == 0
