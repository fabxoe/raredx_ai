# AGENTS.md

## Coding Principles

* Python 3.12
* Type hints required
* Pydantic v2
* Async-first FastAPI design
* Modular architecture
* Testable components
* Clear separation between retrieval and reasoning

---

## Architecture Rules

Preferred modules:

app/

api/
services/
retrieval/
embedding/
reranking/
graph/
llm/
database/
schemas/
tests/

---

## Retrieval Layer

Responsibilities:

* Phenotype processing
* Embedding search
* Candidate generation

Should NOT:

* Generate explanations
* Access LLM directly

---

## Graph Layer

Responsibilities:

* Neo4j queries
* Graph path extraction
* Candidate evidence gathering

Should NOT:

* Perform LLM prompting

---

## Reranking Layer

Responsibilities:

* IC scoring
* Graph scoring
* Embedding similarity
* Learning-to-rank experiments

Outputs:

Candidate disease list with scores

---

## LLM Layer

Responsibilities:

* Explanation generation
* Result summarization

Should consume:

Structured evidence

Should NOT:

Invent evidence

---

## Explainability Rules

Every disease candidate should contain:

* Matching phenotypes
* Missing phenotypes
* Associated genes
* Graph path evidence

---

## Database Rules

Neo4j:

Store:

* Disease nodes
* Gene nodes
* Phenotype nodes

PostgreSQL:

Store:

* User data
* Session data
* Evaluation logs

---

## Research Constraints

Assume:

* Limited labeled data
* Small clinical dataset
* No MIMIC access

Avoid architectures requiring millions of labeled examples.

---

## Preferred Libraries

API:

* FastAPI

Graph:

* neo4j

Embeddings:

* sentence-transformers

ML:

* PyTorch

Vector Search:

* FAISS

Data:

* pandas
* numpy

Testing:

* pytest

---

## Performance Goals

Target retrieval latency:

< 2 seconds

Target graph query latency:

< 1 second

Target full response:

< 5 seconds

---

## Development Philosophy

Prioritize:

1. Interpretability
2. Reproducibility
3. Scientific validity
4. Maintainability

before raw model complexity.
