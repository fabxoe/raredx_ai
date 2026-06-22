from app.database.neo4j import Neo4jClient


CONSTRAINTS = [
    "CREATE CONSTRAINT disease_id IF NOT EXISTS FOR (d:Disease) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT phenotype_id IF NOT EXISTS FOR (p:Phenotype) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT gene_id IF NOT EXISTS FOR (g:Gene) REQUIRE g.id IS UNIQUE",
]


async def ensure_schema(client: Neo4jClient) -> None:
    async with client.session() as session:
        for query in CONSTRAINTS:
            await session.run(query)

