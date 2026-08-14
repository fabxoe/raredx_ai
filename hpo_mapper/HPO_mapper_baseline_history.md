# HPO Mapper Baseline History

This document tracks baseline configuration, experiment settings, evaluation results, and observations for the HPO mapper implementation in `mapper (1).py`.

## Baseline Definition
- Baseline source: `mapper (1).py`
- Development plan source: `HPO_Mapper_Development_Plan.md`
- Purpose: Establish a reproducible starting point and track performance changes over time.
- Core improvement direction: expand from single-symptom mapping to multi-phenotype extraction plus independent HPO mapping.

## Baseline Configuration
- `top_k`: 10
- `threshold`: 0.40
- `deduplicate_hpo`: true
- `backend`: `sentence-transformers`
- `model_name`: `sentence-transformers/all-MiniLM-L6-v2`
- `top_k_per_phrase`: 5
- Phrase extraction: rule-based sentence splitting and list splitting
- Candidate aggregation: deduplicate accepted phrase-level HPO candidates into patient HPO set
- Index files:
  - `data/processed/hpo_terms.csv`
  - `data/processed/hpo_terms_index.csv`
  - `data/processed/hpo_embeddings.npy`

## Current Pipeline

```text
Clinical Note
↓
Phenotype Phrase Extraction
↓
Individual Phrase Embedding
↓
Semantic Similarity Search
↓
Top-K / Threshold
↓
HPO Candidates
↓
Final HPO Set
```

## Evaluation Checklist

### 1. Phenotype Detection

| Metric | Value | Notes |
|--------|-------|-------|
| Detection Precision | TBD | Correctly extracted phenotype phrases / all extracted phrases |
| Detection Recall | TBD | Correctly extracted phenotype phrases / gold phenotype phrases |
| Detection F1 | TBD | Harmonic mean of precision and recall |
| Missed Phenotype List | TBD | Gold phenotype phrases not extracted |
| Wrongly Extracted Phrase List | TBD | Extracted phrases that are not true phenotypes |

### 2. HPO Mapping

| Category | Count / Rate | Notes |
|----------|--------------|-------|
| Exact Match | TBD | Predicted HPO exactly matches gold HPO |
| Ancestor / Descendant Match | TBD | Predicted HPO is hierarchically close to gold HPO |
| Wrong Mapping | TBD | Predicted HPO is clinically incorrect |
| Over-specific Mapping | TBD | Predicted HPO is too specific |
| Under-specific Mapping | TBD | Predicted HPO is too broad |

## Experiment Plan

| Experiment | Extraction | Mapping | Threshold | Graph Input | Status | Result Summary |
|------------|------------|---------|-----------|-------------|--------|----------------|
| A | Existing method | Single symptom | Adjustable | Binary | Planned | TBD |
| B | Multi-phenotype | Top-1 | None | Binary | Planned | TBD |
| C | Multi-phenotype | Top-3 | 0.80 | Binary | Planned | TBD |
| D | Multi-phenotype | Top-5 | 0.80 | Binary | Planned | TBD |
| E | Multi-phenotype | Top-5 | 0.85 | Binary | Planned | TBD |
| F | Multi-phenotype | Top-5 | 0.80 | Similarity-weighted | Planned | TBD |
| G | Multi-phenotype + Ontology Filtering | Top-5 | 0.80 | Similarity-weighted | Planned | TBD |

## Experiment Log Template

### Experiment ID: TBD
- Date:
- Code version / file:
- Dataset / test notes:
- Number of clinical notes:
- Extraction method:
- Mapping strategy:
- `top_k`:
- `top_k_per_phrase`:
- `threshold`:
- Deduplication:
- Graph input:

#### Detection Results
| Metric | Value |
|--------|-------|
| Precision | TBD |
| Recall | TBD |
| F1 | TBD |

#### Mapping Results
| Metric / Category | Value |
|-------------------|-------|
| Exact Match | TBD |
| Ancestor / Descendant Match | TBD |
| Wrong Mapping | TBD |
| Over-specific Mapping | TBD |
| Under-specific Mapping | TBD |

#### Error Analysis
| Type | Examples | Possible Fix |
|------|----------|--------------|
| Missed phenotype | TBD | TBD |
| Wrongly extracted phrase | TBD | TBD |
| Wrong HPO mapping | TBD | TBD |
| Family history confusion | TBD | Family History Filtering |
| Negation confusion | TBD | Negation Detection |
| Temporal context confusion | TBD | Temporal Context Handling |

#### Notes
- Key observation:
- What improved:
- What got worse:
- Next action:

## History

| Date | Version / Note | Score / Metric | Changed Hyperparameters | Comments |
|------|----------------|----------------|-------------------------|----------|
| 2026-06-25 | Initial baseline established | TBD | See baseline configuration | Baseline version created from current `mapper (1).py`. |
| 2026-06-25 | Multi-phenotype pipeline documented | TBD | `top_k_per_phrase=5`, `threshold=0.40` | Development plan converted into experiment tracking format. |

## Usage Notes
- Record evaluation scores and dataset details in the experiment log before updating the summary history table.
- Keep the initial baseline entry untouched so it remains the reference point.
- For each experiment, compare both phenotype detection quality and HPO mapping quality.
- Track whether errors come from phrase extraction, semantic retrieval, thresholding, or downstream graph input design.
- Use the A-G experiment plan as the default roadmap unless the mapper architecture changes.
