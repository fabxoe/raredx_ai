# PROJECT_CONTEXT.md

Project Name: RARE_DX_AI

## Objective

RARE_DX_AI is an explainable rare disease diagnostic support system that uses phenotype information to rank candidate diseases and provide evidence-based explanations.

The system is intended for research and clinical decision support, not autonomous diagnosis.

Primary goal:

Input:

* Clinical notes
* HPO terms
* Optional gene list

Output:

* Ranked rare disease candidates
* Disease-gene associations
* Phenotype matching evidence
* Explainable reasoning path

---

## Research Motivation

Existing tools such as:

* Phenomizer
* Exomizer
* LIRICAL

primarily rely on ontology similarity, Information Content (IC), and likelihood-based ranking.

This project investigates whether modern representation learning and graph-based methods can improve disease ranking and explainability.

---

## Available Data Sources

Primary resources:

* Human Phenotype Ontology (HPO)
* HPO Annotations
* Disease ↔ Phenotype mappings
* Disease ↔ Gene mappings
* Gene ↔ Phenotype mappings

Potential future resources:

* OMIM
* Orphanet
* ClinVar
* PubMed-derived knowledge

Current assumption:

The project should remain functional even when OMIM and Orphanet are unavailable.

---

## Current Research Directions

### Direction A

Classical Retrieval

Phenotype
→ IC Weighting
→ Similarity Scoring
→ Disease Ranking

Reference systems:

* Phenomizer
* LIRICAL

---

### Direction B

Embedding + Knowledge Graph

Phenotype
→ Embedding Model
→ Candidate Retrieval
→ Neo4j Knowledge Graph
→ Graph-based Re-ranking
→ Explanation Generation

Target outcome:

Improved ranking quality and better interpretability.

---

## Knowledge Graph Design

Main node types:

* Disease
* Gene
* Phenotype(HPO)

Relationships:

Disease - HAS_PHENOTYPE -> Phenotype

Disease - ASSOCIATED_WITH -> Gene

Gene - ASSOCIATED_PHENOTYPE -> Phenotype

Possible future:

* Drug
* Publication
* Pathway

---

## Neo4j Usage

Neo4j is not only a storage layer.

Expected roles:

* Graph retrieval
* Path reasoning
* Disease evidence aggregation
* Explainability generation
* Candidate reranking

---

## Embedding Research

Potential embedding targets:

1. HPO Term Embedding

Input:

* HPO term name
* HPO definition

Output:

* Phenotype vector

---

2. Disease Embedding

Input:

* Associated phenotype set

Output:

* Disease representation vector

---

3. Patient Embedding

Input:

* Extracted phenotype set

Output:

* Patient phenotype representation

---

Similarity computation:

Patient Vector
vs
Disease Vector

using:

* Cosine Similarity
* Learned Similarity
* Contrastive Learning

---

## Future Deep Learning Experiments

Potential methods:

* Contrastive Learning
* Triplet Loss
* Hard Negative Mining
* Learning-to-Rank
* Cross Encoder Re-ranking
* Graph Neural Networks

Candidate GNNs:

* GCN
* GraphSAGE
* GAT

Research question:

Can graph-aware representations outperform IC-based disease ranking?

---

## Explainability Requirements

Every prediction should include evidence.

Examples:

Disease: Rett Syndrome

Evidence:

* Developmental delay
* Seizure
* Microcephaly

Graph Path:

Patient
→ Phenotype
→ Disease
→ Gene

The system should explain why a disease was ranked highly.

---

## Clinical Constraints

This system is NOT a diagnostic device.

It is a candidate prioritization tool.

Output language should avoid:

* "Diagnosed as"
* "Confirmed disease"

Preferred wording:

* Candidate disease
* Prioritized disease
* Possible association

---

## Evaluation Metrics

Primary:

* Top-1 Accuracy
* Top-5 Accuracy
* Top-10 Accuracy
* MRR
* NDCG

Secondary:

* Explainability quality
* Graph coverage
* Retrieval latency

---

## Current Technology Stack

Backend:

* FastAPI

Database:

* Neo4j
* PostgreSQL

Vector Search:

* FAISS

AI Framework:

* PyTorch

LLM Layer:

* OpenAI API compatible

Deployment:

* Docker

---

## Long-Term Vision

Build an explainable phenotype-driven rare disease reasoning system that combines:

* Ontology
* Embeddings
* Knowledge Graphs
* LLM Explanations

while remaining scientifically interpretable.
