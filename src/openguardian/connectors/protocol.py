from typing import AsyncIterator, Protocol
from openguardian.models.graph_event import GraphEvent

class ConnectorProtocol(Protocol):
    """
    Interface definition that all data source connectors must implement.
    """
    @property
    def connector_id(self) -> str:
        """Returns the unique identifier of the connector plugin."""
        ...

    async def start(self) -> None:
        """Lifecycle hook executed when the application boots."""
        ...

    async def stop(self) -> None:
        """Lifecycle hook executed when the application shuts down."""
        ...

    async def poll(self) -> AsyncIterator[GraphEvent]:
        """
        Incrementally yields events. Must be an async generator.
        Should handle checkpointing natively so restarted polls resume safely.
        """
        ...
        yield GraphEvent(
            timestamp="1970-01-01T00:00:00Z", # type: ignore
            source="mock",
            user_id="mock",
            event_type="mock",
            category="mock"
        )
