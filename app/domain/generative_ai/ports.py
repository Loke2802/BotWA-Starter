from typing import Protocol

from pydantic import BaseModel

from app.domain.generative_ai.contracts import Generation


class AIProvider(Protocol):
    async def generate(
        self, *, stage: str, context: str, schema: type[BaseModel]
    ) -> Generation: ...
