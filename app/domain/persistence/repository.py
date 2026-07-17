from abc import ABC, abstractmethod
from uuid import UUID


class IRepository[T](ABC):
    @abstractmethod
    def add(self, entity: T) -> None: ...

    @abstractmethod
    def get(self, id: UUID) -> T | None: ...

    @abstractmethod
    def list(self, **filters: object) -> list[T]: ...

    @abstractmethod
    def update(self, entity: T) -> None: ...

    @abstractmethod
    def delete(self, id: UUID) -> bool: ...
