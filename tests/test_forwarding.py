"""Tests for command forwarding pipeline."""

import pytest

from imap_granular_access_proxy.forwarding import (
    ForwardedCommand,
    ForwardingPipeline,
)


class MockSender:
    """Mock sender for testing that records all sent lines."""

    def __init__(self) -> None:
        self.sent_lines: list[bytes] = []

    def sendLine(self, line: bytes) -> None:
        self.sent_lines.append(line)


class TestForwardedCommand:
    """Tests for ForwardedCommand dataclass."""

    def test_creation(self) -> None:
        """ForwardedCommand should store all provided fields."""
        cmd = ForwardedCommand(
            client_tag=b"A001",
            upstream_tag=b"P0001",
            command="SELECT",
            args=b"INBOX",
        )
        assert cmd.client_tag == b"A001"
        assert cmd.upstream_tag == b"P0001"
        assert cmd.command == "SELECT"
        assert cmd.args == b"INBOX"

    def test_timestamp_auto_set(self) -> None:
        """ForwardedCommand should auto-set timestamp."""
        cmd = ForwardedCommand(
            client_tag=b"A001",
            upstream_tag=b"P0001",
            command="SELECT",
            args=None,
        )
        assert cmd.timestamp > 0

    def test_args_can_be_none(self) -> None:
        """ForwardedCommand should accept None for args."""
        cmd = ForwardedCommand(
            client_tag=b"A001",
            upstream_tag=b"P0001",
            command="NOOP",
            args=None,
        )
        assert cmd.args is None


class TestForwardingPipelineBasics:
    """Basic tests for ForwardingPipeline."""

    def test_initial_state(self) -> None:
        """Pipeline should start with no in-flight commands."""
        pipeline = ForwardingPipeline()
        assert pipeline.in_flight_count == 0
        assert len(pipeline.in_flight_client_tags) == 0

    def test_generate_upstream_tag_increments(self) -> None:
        """generate_upstream_tag should produce incrementing tags."""
        pipeline = ForwardingPipeline()
        assert pipeline.generate_upstream_tag() == b"P0001"
        assert pipeline.generate_upstream_tag() == b"P0002"
        assert pipeline.generate_upstream_tag() == b"P0003"


class TestForwardCommand:
    """Tests for ForwardingPipeline.forward_command."""

    def test_forward_command_without_args(self) -> None:
        """forward_command should send command without args."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()

        cmd = pipeline.forward_command(
            client_tag=b"A001",
            command="NOOP",
            args=None,
            upstream=upstream,
        )

        assert cmd.client_tag == b"A001"
        assert cmd.upstream_tag == b"P0001"
        assert cmd.command == "NOOP"
        assert len(upstream.sent_lines) == 1
        assert upstream.sent_lines[0] == b"P0001 NOOP"

    def test_forward_command_with_args(self) -> None:
        """forward_command should send command with args."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()

        cmd = pipeline.forward_command(
            client_tag=b"A002",
            command="SELECT",
            args=b"INBOX",
            upstream=upstream,
        )

        assert cmd.args == b"INBOX"
        assert len(upstream.sent_lines) == 1
        assert upstream.sent_lines[0] == b"P0001 SELECT INBOX"

    def test_forward_command_tracks_in_flight(self) -> None:
        """forward_command should track the command as in-flight."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()

        pipeline.forward_command(
            client_tag=b"A001",
            command="SELECT",
            args=b"INBOX",
            upstream=upstream,
        )

        assert pipeline.in_flight_count == 1
        assert b"A001" in pipeline.in_flight_client_tags

    def test_forward_multiple_commands(self) -> None:
        """forward_command should handle multiple concurrent commands."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()

        pipeline.forward_command(b"A001", "NOOP", None, upstream)
        pipeline.forward_command(b"A002", "SELECT", b"INBOX", upstream)
        pipeline.forward_command(b"A003", "CAPABILITY", None, upstream)

        assert pipeline.in_flight_count == 3
        assert upstream.sent_lines == [
            b"P0001 NOOP",
            b"P0002 SELECT INBOX",
            b"P0003 CAPABILITY",
        ]

    def test_forward_duplicate_client_tag_raises(self) -> None:
        """forward_command should raise on duplicate client tag."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()

        pipeline.forward_command(b"A001", "NOOP", None, upstream)

        with pytest.raises(ValueError, match="already in flight"):
            pipeline.forward_command(b"A001", "CAPABILITY", None, upstream)


class TestRouteResponse:
    """Tests for ForwardingPipeline.route_response."""

    def test_route_tagged_ok_response(self) -> None:
        """route_response should rewrite tag on OK response."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()
        client = MockSender()

        pipeline.forward_command(b"A001", "NOOP", None, upstream)

        result = pipeline.route_response(b"P0001 OK NOOP completed", client)

        assert result is True
        assert len(client.sent_lines) == 1
        assert client.sent_lines[0] == b"A001 OK NOOP completed"
        assert pipeline.in_flight_count == 0

    def test_route_tagged_no_response(self) -> None:
        """route_response should rewrite tag on NO response."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()
        client = MockSender()

        pipeline.forward_command(b"A001", "SELECT", b"INBOX", upstream)

        result = pipeline.route_response(b"P0001 NO Mailbox not found", client)

        assert result is True
        assert client.sent_lines[0] == b"A001 NO Mailbox not found"

    def test_route_tagged_bad_response(self) -> None:
        """route_response should rewrite tag on BAD response."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()
        client = MockSender()

        pipeline.forward_command(b"A001", "BOGUS", None, upstream)

        result = pipeline.route_response(b"P0001 BAD Unknown command", client)

        assert result is True
        assert client.sent_lines[0] == b"A001 BAD Unknown command"

    def test_route_untagged_response(self) -> None:
        """route_response should pass through untagged responses."""
        pipeline = ForwardingPipeline()
        client = MockSender()

        result = pipeline.route_response(b"* 5 EXISTS", client)

        assert result is False
        assert client.sent_lines[0] == b"* 5 EXISTS"

    def test_route_capability_response(self) -> None:
        """route_response should pass through untagged CAPABILITY."""
        pipeline = ForwardingPipeline()
        client = MockSender()

        result = pipeline.route_response(
            b"* CAPABILITY IMAP4rev1 IDLE NAMESPACE", client
        )

        assert result is False
        assert client.sent_lines[0] == b"* CAPABILITY IMAP4rev1 IDLE NAMESPACE"

    def test_route_continuation(self) -> None:
        """route_response should pass through continuation requests."""
        pipeline = ForwardingPipeline()
        client = MockSender()

        result = pipeline.route_response(b"+ Ready for literal data", client)

        assert result is False
        assert client.sent_lines[0] == b"+ Ready for literal data"

    def test_route_empty_line(self) -> None:
        """route_response should handle empty lines."""
        pipeline = ForwardingPipeline()
        client = MockSender()

        result = pipeline.route_response(b"", client)

        assert result is False
        assert len(client.sent_lines) == 0

    def test_route_unknown_tag_passes_through(self) -> None:
        """route_response should pass through responses with unknown tags."""
        pipeline = ForwardingPipeline()
        client = MockSender()

        # No command forwarded, so this tag is unknown
        result = pipeline.route_response(b"UNKNOWN OK Something", client)

        assert result is False
        assert client.sent_lines[0] == b"UNKNOWN OK Something"

    def test_route_multiple_responses_in_order(self) -> None:
        """route_response should handle interleaved responses correctly."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()
        client = MockSender()

        pipeline.forward_command(b"A001", "SELECT", b"INBOX", upstream)
        pipeline.forward_command(b"A002", "FETCH", b"1 BODY[]", upstream)

        # Responses come back (with some untagged first)
        pipeline.route_response(b"* 5 EXISTS", client)
        pipeline.route_response(b"* 2 RECENT", client)
        pipeline.route_response(b"P0001 OK SELECT completed", client)
        pipeline.route_response(b"* 1 FETCH (BODY[] {100})", client)
        pipeline.route_response(b"P0002 OK FETCH completed", client)

        assert client.sent_lines == [
            b"* 5 EXISTS",
            b"* 2 RECENT",
            b"A001 OK SELECT completed",
            b"* 1 FETCH (BODY[] {100})",
            b"A002 OK FETCH completed",
        ]
        assert pipeline.in_flight_count == 0


class TestLookupMethods:
    """Tests for lookup methods."""

    def test_get_forwarded_by_client_tag(self) -> None:
        """get_forwarded_by_client_tag should find forwarded commands."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()

        sent_cmd = pipeline.forward_command(b"A001", "NOOP", None, upstream)
        found_cmd = pipeline.get_forwarded_by_client_tag(b"A001")

        assert found_cmd is sent_cmd

    def test_get_forwarded_by_client_tag_not_found(self) -> None:
        """get_forwarded_by_client_tag should return None if not found."""
        pipeline = ForwardingPipeline()

        assert pipeline.get_forwarded_by_client_tag(b"NOTEXIST") is None

    def test_get_forwarded_by_upstream_tag(self) -> None:
        """get_forwarded_by_upstream_tag should find forwarded commands."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()

        sent_cmd = pipeline.forward_command(b"A001", "NOOP", None, upstream)
        found_cmd = pipeline.get_forwarded_by_upstream_tag(b"P0001")

        assert found_cmd is sent_cmd

    def test_get_forwarded_by_upstream_tag_not_found(self) -> None:
        """get_forwarded_by_upstream_tag should return None if not found."""
        pipeline = ForwardingPipeline()

        assert pipeline.get_forwarded_by_upstream_tag(b"P9999") is None


class TestCleanup:
    """Tests for cleanup methods."""

    def test_clear_all(self) -> None:
        """clear_all should remove all in-flight commands."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()

        pipeline.forward_command(b"A001", "NOOP", None, upstream)
        pipeline.forward_command(b"A002", "CAPABILITY", None, upstream)

        count = pipeline.clear_all()

        assert count == 2
        assert pipeline.in_flight_count == 0
        assert pipeline.get_forwarded_by_client_tag(b"A001") is None

    def test_clear_all_empty_pipeline(self) -> None:
        """clear_all should return 0 on empty pipeline."""
        pipeline = ForwardingPipeline()

        count = pipeline.clear_all()

        assert count == 0

    def test_cancel_by_client_tag(self) -> None:
        """cancel_by_client_tag should remove specific command."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()

        pipeline.forward_command(b"A001", "NOOP", None, upstream)
        pipeline.forward_command(b"A002", "CAPABILITY", None, upstream)

        cancelled = pipeline.cancel_by_client_tag(b"A001")

        assert cancelled is not None
        assert cancelled.client_tag == b"A001"
        assert pipeline.in_flight_count == 1
        assert pipeline.get_forwarded_by_client_tag(b"A002") is not None

    def test_cancel_by_client_tag_not_found(self) -> None:
        """cancel_by_client_tag should return None if not found."""
        pipeline = ForwardingPipeline()

        cancelled = pipeline.cancel_by_client_tag(b"NOTEXIST")

        assert cancelled is None

    def test_client_tag_reusable_after_completion(self) -> None:
        """Client tags should be reusable after command completes."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()
        client = MockSender()

        # First command with A001
        pipeline.forward_command(b"A001", "NOOP", None, upstream)
        pipeline.route_response(b"P0001 OK NOOP completed", client)

        # Should be able to reuse A001
        pipeline.forward_command(b"A001", "CAPABILITY", None, upstream)
        assert pipeline.in_flight_count == 1

    def test_client_tag_reusable_after_cancel(self) -> None:
        """Client tags should be reusable after command is cancelled."""
        pipeline = ForwardingPipeline()
        upstream = MockSender()

        pipeline.forward_command(b"A001", "NOOP", None, upstream)
        pipeline.cancel_by_client_tag(b"A001")

        # Should be able to reuse A001
        pipeline.forward_command(b"A001", "CAPABILITY", None, upstream)
        assert pipeline.in_flight_count == 1
