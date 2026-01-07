"""Tests for upstream IMAP client infrastructure."""

import pytest
from twisted.internet import protocol
from twisted.mail import imap4

from imap_granular_access_proxy.upstream import (
    UpstreamConfig,
    UpstreamIMAPClientFactory,
    UpstreamIMAPProtocol,
)


@pytest.fixture
def sample_config() -> UpstreamConfig:
    """Create a sample UpstreamConfig for testing."""
    return UpstreamConfig(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="test-password-for-unit-tests",  # noqa: S106
    )


class TestUpstreamConfig:
    """Tests for UpstreamConfig dataclass."""

    def test_creation_with_required_fields(self, sample_config: UpstreamConfig) -> None:
        """UpstreamConfig should be creatable with required fields."""
        assert sample_config.host == "imap.example.com"
        assert sample_config.port == 993
        assert sample_config.username == "user@example.com"
        assert sample_config.password == "test-password-for-unit-tests"  # noqa: S105

    def test_use_tls_defaults_to_true(self, sample_config: UpstreamConfig) -> None:
        """use_tls should default to True."""
        assert sample_config.use_tls is True

    def test_use_tls_can_be_disabled(self) -> None:
        """use_tls should be settable to False."""
        config = UpstreamConfig(
            host="imap.example.com",
            port=143,
            username="user@example.com",
            password="test-password-for-unit-tests",  # noqa: S106
            use_tls=False,
        )
        assert config.use_tls is False

    def test_config_is_immutable(self, sample_config: UpstreamConfig) -> None:
        """UpstreamConfig should be frozen (immutable)."""
        try:
            sample_config.host = "other.example.com"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass  # Expected for frozen dataclass


class TestUpstreamIMAPProtocol:
    """Tests for UpstreamIMAPProtocol."""

    def test_inherits_from_imap4_client(self) -> None:
        """Protocol should inherit from twisted.mail.imap4.IMAP4Client."""
        assert issubclass(UpstreamIMAPProtocol, imap4.IMAP4Client)

    def test_protocol_instantiation(self) -> None:
        """Protocol should be instantiable."""
        proto = UpstreamIMAPProtocol()
        assert proto is not None

    def test_greeting_deferred_initially_none(self) -> None:
        """_greeting_deferred should be None initially."""
        proto = UpstreamIMAPProtocol()
        assert proto._greeting_deferred is None


class TestUpstreamIMAPClientFactory:
    """Tests for UpstreamIMAPClientFactory."""

    def test_inherits_from_client_factory(self) -> None:
        """Factory should inherit from twisted.internet.protocol.ClientFactory."""
        assert issubclass(UpstreamIMAPClientFactory, protocol.ClientFactory)

    def test_factory_instantiation(self, sample_config: UpstreamConfig) -> None:
        """Factory should be instantiable with UpstreamConfig."""
        factory = UpstreamIMAPClientFactory(sample_config)
        assert factory.config is sample_config

    def test_factory_protocol_class(self) -> None:
        """Factory should use UpstreamIMAPProtocol as protocol class."""
        assert UpstreamIMAPClientFactory.protocol is UpstreamIMAPProtocol

    def test_build_protocol_returns_upstream_protocol(
        self, sample_config: UpstreamConfig
    ) -> None:
        """buildProtocol should return an UpstreamIMAPProtocol instance."""
        factory = UpstreamIMAPClientFactory(sample_config)

        class MockAddress:
            host = "imap.example.com"
            port = 993

        proto = factory.buildProtocol(MockAddress())  # type: ignore[arg-type]
        assert isinstance(proto, UpstreamIMAPProtocol)
        assert proto.factory is factory

    def test_build_protocol_stores_reference(
        self, sample_config: UpstreamConfig
    ) -> None:
        """buildProtocol should store a reference to the protocol."""
        factory = UpstreamIMAPClientFactory(sample_config)

        class MockAddress:
            host = "imap.example.com"
            port = 993

        proto = factory.buildProtocol(MockAddress())  # type: ignore[arg-type]
        assert factory._protocol is proto

    def test_initial_connection_deferred_is_none(
        self, sample_config: UpstreamConfig
    ) -> None:
        """_connection_deferred should be None initially."""
        factory = UpstreamIMAPClientFactory(sample_config)
        assert factory._connection_deferred is None
