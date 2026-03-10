import logging
from neo4j import AsyncGraphDatabase, AsyncDriver
from openguardian.config.settings import settings

logger = logging.getLogger(__name__)

class GraphClient:
    """
    Manages the Neo4j AsyncDriver connection pool for the entire application.
    """
    def __init__(self):
        self._driver: AsyncDriver | None = None

    def get_driver(self) -> AsyncDriver:
        """
        Retrieves the singleton Neo4j AsyncDriver instance.
        Validates the configuration and initializes the driver if not already open.
        """
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
            )
        return self._driver

    async def verify_connectivity(self) -> bool:
        """
        Pings the Neo4j database to ensure the connection is active and credentials are correct.
        """
        driver = self.get_driver()
        try:
            await driver.verify_connectivity()
            logger.info("Neo4j connectivity verified")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            return False

    async def close(self):
        """
        Closes the underlying driver pool gracefully.
        """
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j driver connection closed")

# Global singleton client instance
graph_client = GraphClient()
