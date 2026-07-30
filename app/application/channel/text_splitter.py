from app.domain.channel.contracts import OutboundChannelMessage


def split_outbound_message(
    message: OutboundChannelMessage,
    *,
    max_length: int,
) -> tuple[OutboundChannelMessage, ...]:
    if max_length < 1:
        raise ValueError("max_length must be positive")
    text = message.text
    if len(text) <= max_length:
        return (message,)

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break
        boundary = remaining.rfind("\n", 0, max_length + 1)
        if boundary <= 0:
            boundary = remaining.rfind(" ", 0, max_length + 1)
        if boundary <= 0:
            boundary = max_length
        chunk = remaining[:boundary].rstrip()
        if not chunk:
            chunk = remaining[:max_length]
            boundary = max_length
        chunks.append(chunk)
        remaining = remaining[boundary:].lstrip()

    return tuple(
        message.model_copy(update={"text": chunk}) for chunk in chunks if chunk
    )
