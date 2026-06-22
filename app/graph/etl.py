from app.database.neo4j import Neo4jClient
from app.etl.models import KnowledgeBase
from app.graph.schema import ensure_schema


async def load_knowledge_into_neo4j(client: Neo4jClient, kb: KnowledgeBase) -> None:
    await ensure_schema(client)
    await _upsert_phenotypes(client, kb)
    await _upsert_disease_phenotypes(client, kb)
    await _upsert_gene_phenotypes(client, kb)


async def _upsert_phenotypes(client: Neo4jClient, kb: KnowledgeBase) -> None:
    rows = [
        {
            "id": term.hpo_id,
            "name": term.name,
            "definition": term.definition,
            "parents": list(term.parents),
        }
        for term in kb.phenotypes.values()
    ]
    query = """
    UNWIND $rows AS row
    MERGE (p:Phenotype {id: row.id})
    SET p.name = row.name,
        p.definition = row.definition
    WITH p, row
    UNWIND row.parents AS parent_id
    MERGE (parent:Phenotype {id: parent_id})
    MERGE (p)-[:IS_A]->(parent)
    """
    async with client.session() as session:
        await session.run(query, rows=rows)


async def _upsert_disease_phenotypes(client: Neo4jClient, kb: KnowledgeBase) -> None:
    rows = [annotation.__dict__ for annotation in kb.disease_phenotypes]
    query = """
    UNWIND $rows AS row
    MERGE (d:Disease {id: row.disease_id})
    SET d.name = row.disease_name,
        d.source = split(row.disease_id, ':')[0]
    MERGE (p:Phenotype {id: row.hpo_id})
    MERGE (d)-[r:HAS_PHENOTYPE]->(p)
    SET r.frequency = row.frequency,
        r.evidence = row.evidence,
        r.source = row.source
    """
    async with client.session() as session:
        await session.run(query, rows=rows)


async def _upsert_gene_phenotypes(client: Neo4jClient, kb: KnowledgeBase) -> None:
    rows = [annotation.__dict__ for annotation in kb.gene_phenotypes]
    query = """
    UNWIND $rows AS row
    MERGE (g:Gene {id: row.gene_id})
    SET g.symbol = row.gene_symbol
    MERGE (p:Phenotype {id: row.hpo_id})
    MERGE (g)-[:ASSOCIATED_PHENOTYPE]->(p)
    WITH row, g
    WHERE row.disease_id IS NOT NULL
    MERGE (d:Disease {id: row.disease_id})
    SET d.name = coalesce(row.disease_name, d.name),
        d.source = split(row.disease_id, ':')[0]
    MERGE (d)-[:ASSOCIATED_WITH]->(g)
    """
    async with client.session() as session:
        await session.run(query, rows=rows)

