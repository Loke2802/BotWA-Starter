import pytest
from app.core.conversation.channel_adapter import ChannelAdapter, HttpChannelAdapter
from app.domain.conversation.contracts import ChannelResponse
from app.domain.conversation.response import BusinessResponse


def test_channel_adapter_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        ChannelAdapter()  # type: ignore[abstract]


def test_http_adapter_adapt_returns_channel_response() -> None:
    adapter = HttpChannelAdapter()
    response = BusinessResponse(
        message="Hello",
        status="accepted",
    )

    result = adapter.adapt(response)

    assert isinstance(result, ChannelResponse)
    assert result.message == "Hello"
    assert result.status == "accepted"


def test_http_adapter_copies_status_and_message() -> None:
    adapter = HttpChannelAdapter()
    response = BusinessResponse(
        message="Gracias por tu mensaje.",
        status="accepted",
        tone="friendly",
    )

    result = adapter.adapt(response)

    assert result.message == "Gracias por tu mensaje."
    assert result.status == "accepted"


def test_http_adapter_ignores_tone() -> None:
    adapter = HttpChannelAdapter()
    response = BusinessResponse(
        message="Test",
        status="accepted",
        tone="empathetic",
    )

    result = adapter.adapt(response)

    assert result.message == "Test"
    assert result.status == "accepted"


def test_http_adapter_with_rejected_status() -> None:
    adapter = HttpChannelAdapter()
    response = BusinessResponse(
        message="La conversación se encuentra finalizada.",
        status="rejected",
    )

    result = adapter.adapt(response)

    assert result.message == "La conversación se encuentra finalizada."
    assert result.status == "rejected"
