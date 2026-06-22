import argparse
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.database.neo4j import Neo4jClient
from app.etl.processed_store import load_processed_knowledge_base
from app.graph.etl import load_knowledge_into_neo4j


async def run(processed_dir: Path) -> None:
    settings = get_settings()
    kb = load_processed_knowledge_base(processed_dir)
    client = Neo4jClient(settings)
    try:
        await load_knowledge_into_neo4j(client, kb)
    finally:
        await client.close()
    print("Neo4j knowledge graph load completed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load processed RARE_DX_AI knowledge into Neo4j.")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    asyncio.run(run(args.processed_dir))


if __name__ == "__main__":
    main()
