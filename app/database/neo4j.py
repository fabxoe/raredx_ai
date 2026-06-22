from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import Settings


class Neo4jClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._driver: AsyncDriver | None = None

    async def driver(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user, self.settings.neo4j_password),
            )
        return self._driver

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    @asynccontextmanager
    async def session(self) -> AsyncIterator[object]:
        driver = await self.driver()
        async with driver.session(database=self.settings.neo4j_database) as session:
            yield session

    async def verify_connectivity(self) -> None:
        driver = await self.driver()
        await driver.verify_connectivity()

