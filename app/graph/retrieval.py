from app.database.neo4j import Neo4jClient
from app.schemas.retrieval import CandidateDisease, MatchedPhenotype, ScoreComponents


class GraphRetrievalService:
    def __init__(self, client: Neo4jClient) -> None:
        self.client = client

    async def evidence_for_query(
        self,
        hpo_terms: list[str],
        top_k: int,
        disease_ids: list[str] | None = None,
    ) -> list[CandidateDisease]:
        query = """
        MATCH (d:Disease)-[r:HAS_PHENOTYPE]->(p:Phenotype)
        WHERE p.id IN $hpo_terms
          AND ($disease_ids IS NULL OR d.id IN $disease_ids)
        WITH d, collect({id: p.id, name: p.name, frequency: r.frequency, evidence: r.evidence}) AS matched
        OPTIONAL MATCH (d)-[:HAS_PHENOTYPE]->(allp:Phenotype)
        WITH d, matched, collect(DISTINCT allp.id) AS all_hpo
        OPTIONAL MATCH (d)-[:ASSOCIATED_WITH]->(g:Gene)
        WITH d, matched, all_hpo, collect(DISTINCT g.symbol) AS genes
        RETURN d.id AS disease_id,
               d.name AS disease_name,
               matched,
               [hpo IN $hpo_terms WHERE NOT hpo IN all_hpo] AS missing_hpo,
               genes,
               toFloat(size(matched)) / toFloat(size($hpo_terms)) AS graph_score
        ORDER BY graph_score DESC, disease_name ASC
        LIMIT $top_k
        """
        async with self.client.session() as session:
            result = await session.run(query, hpo_terms=hpo_terms, disease_ids=disease_ids, top_k=top_k)
            rows = await result.data()

        candidates: list[CandidateDisease] = []
        for row in rows:
            matched = [
                MatchedPhenotype(
                    hpo_id=item["id"],
                    name=item.get("name"),
                    frequency=item.get("frequency"),
                    evidence=item.get("evidence"),
                )
                for item in row["matched"]
            ]
            missing = [MatchedPhenotype(hpo_id=hpo_id) for hpo_id in row["missing_hpo"]]
            candidates.append(
                CandidateDisease(
                    disease_id=row["disease_id"],
                    disease_name=row["disease_name"],
                    score=float(row["graph_score"]),
                    score_components=ScoreComponents(graph_score=float(row["graph_score"])),
                    matched_phenotypes=matched,
                    missing_phenotypes=missing,
                    associated_genes=sorted(gene for gene in row["genes"] if gene),
                    graph_paths=[
                        f"Patient -> {phenotype.hpo_id} -> {row['disease_id']}"
                        for phenotype in matched
                    ],
                )
            )
        return candidates

