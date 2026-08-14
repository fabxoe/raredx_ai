# Orphanet HPO Disease Mapping Dataset

## Overview

This document describes the Orphanet disease-HPO mapping datasets generated for the RareDX AI project.

The datasets were created from the Orphanet XML file:

```text
Orphanet/Clinical_signs_and_symptoms_in_rare_disease.xml
```

The source XML contains Orphanet rare disease entries and their associated Human Phenotype Ontology (HPO) clinical signs/symptoms, including frequency labels.

Source XML metadata:

```text
JDBOR date: 2025-12-09 07:09:56
Version: 1.3.42 / 4.1.8 [2025-03-03]
License: Creative Commons Attribution 4.0 International (CC-BY-4.0)
```

The HPO ontology graph used for similarity-related processing is:

```text
data/raw/hp.obo
```

Its header indicates:

```text
data-version: hp/releases/2026-06-23
```

## Generated Files

### 1. Baseline Disease-HPO Mapping

```text
data/processed/HPO_disease_mapping_baseline.csv
```

This is the main baseline dataset. It contains one row per Orphanet disease-HPO association.

Shape:

```text
Rows including header: 115,879
Data rows: 115,878
Unique diseases: 4,335
Unique HPO IDs: 8,701
```

Columns:

| Column | Description |
|---|---|
| `disease_id` | Orphanet disease identifier. Extracted from XML `OrphaCode`. |
| `disease_name` | English Orphanet disease name. Extracted from `Disorder > Name`. |
| `hpo_id` | HPO identifier, for example `HP:0001250`. Extracted from `HPO > HPOId`. |
| `hpo_name` | HPO term name, for example `Seizure`. Extracted from `HPO > HPOTerm`. |
| `frequency_label` | Orphanet frequency label for the disease-HPO association. |

Example:

```csv
disease_id,disease_name,hpo_id,hpo_name,frequency_label
58,Alexander disease,HP:0000256,Macrocephaly,Very frequent (99-80%)
58,Alexander disease,HP:0001249,Intellectual disability,Very frequent (99-80%)
58,Alexander disease,HP:0001250,Seizure,Very frequent (99-80%)
```

Important note:

The source XML reports `HPODisorderSetStatusList count="4337"`, while the extracted baseline contains 4,335 unique disease IDs with HPO association rows. This dataset is therefore best interpreted as the set of disease-HPO annotation rows available in the XML, not as a complete list of every Orphanet disease regardless of whether usable HPO rows exist.

### 2. Frequency Weight Dataset

```text
data/processed/HPO_disease_mapping_with_frequency_weight.csv
```

This file preserves all baseline columns and adds:

| Column | Description |
|---|---|
| `frequency_weight` | Numeric version of `frequency_label`, using midpoint values for percentage ranges. |

Shape:

```text
Rows including header: 115,879
Data rows: 115,878
```

Frequency mapping:

| `frequency_label` | `frequency_weight` | Rule |
|---|---:|---|
| `Obligate (100%)` | `1.000` | Exact 100% |
| `Very frequent (99-80%)` | `0.895` | Midpoint of 0.99 and 0.80 |
| `Frequent (79-30%)` | `0.545` | Midpoint of 0.79 and 0.30 |
| `Occasional (29-5%)` | `0.170` | Midpoint of 0.29 and 0.05 |
| `Very rare (<4-1%)` | `0.025` | Midpoint of 0.04 and 0.01 |
| `Excluded (0%)` | `0.000` | Exact 0% |

Observed label counts in the baseline dataset:

| `frequency_label` | Row count |
|---|---:|
| `Occasional (29-5%)` | 42,753 |
| `Frequent (79-30%)` | 39,588 |
| `Very frequent (99-80%)` | 25,676 |
| `Very rare (<4-1%)` | 6,509 |
| `Excluded (0%)` | 727 |
| `Obligate (100%)` | 625 |

### 3. IC Weight Dataset

```text
data/processed/HPO_disease_mapping_baseline_with_ic.csv
```

This file preserves all baseline columns and adds:

| Column | Description |
|---|---|
| `ic_weight` | Information content of the row's `hpo_id`, computed from disease-level HPO annotations and the HPO ontology graph. |
| `ic_disease_count` | Number of unique diseases annotated with this HPO term or one of its descendants. |
| `ic_total_diseases` | Total unique diseases in the baseline annotation corpus. |
| `ic_frequency` | `ic_disease_count / ic_total_diseases`. |

Shape:

```text
Rows including header: 115,879
Data rows: 115,878
```

Formula:

```text
IC(t) = -log(P(t))
P(t) = N_t / N_total
```

Where:

| Symbol | Meaning |
|---|---|
| `t` | HPO term |
| `N_t` | Number of diseases annotated with HPO term `t` or any descendant of `t` |
| `N_total` | Total number of diseases in the baseline dataset with HPO annotations |

Implementation details:

- Parent-child relationships are parsed from `is_a` edges in `data/raw/hp.obo`.
- Alternative HPO IDs from `alt_id` are normalized to their primary HPO IDs during calculation.
- If an HPO ID is normalized from an `alt_id`, the original value is kept in `hpo_id_original`.
- Obsolete HPO terms are excluded from IC calculation. Rows with obsolete or missing terms receive `NaN` IC values.
- Each disease's direct HPO annotations are propagated to all ancestor HPO terms.
- A broad ancestor term appears in many diseases, so it receives a low IC.
- A rare/specific term appears in fewer diseases, so it receives a high IC.
- Natural logarithm is used.
- Frequency category labels such as `Very frequent (99-80%)` are not used for IC calculation.

Observed IC range in this dataset:

```text
Minimum ic_weight: 0.000000
Maximum ic_weight: 8.374477
```

Example values:

| HPO ID | HPO name | `ic_weight` |
|---|---|---:|
| `HP:0000118` | Phenotypic abnormality | `0.000000` |
| `HP:0001250` | Seizure | `1.268691` |
| `HP:0001263` | Global developmental delay | `1.587760` |
| `HP:0000707` | Abnormality of the nervous system | `0.268867` |
| `HP:0007359` | Focal-onset seizure | `3.499280` |
| `HP:0001355` | Megalencephaly | `5.889570` |

### 4. Patient HPO Similarity Example Dataset

```text
data/processed/HPO_disease_mapping_with_patient_similarity.csv
```

This file was generated as an example using the patient/query HPO IDs:

```text
HP:0001250, HP:0001249, HP:0000256
```

Those correspond to:

```text
Seizure
Intellectual disability
Macrocephaly
```

This file adds two columns:

| Column | Description |
|---|---|
| `hpo_similarity_weight` | The maximum Lin similarity between the row's `hpo_id` and any patient/query HPO ID. |
| `best_matching_query_hpo` | The patient/query HPO ID that produced the maximum similarity for that row. |

Important note:

This similarity file is not a fixed universal dataset. HPO similarity is a pairwise score between a query/patient HPO term and a disease HPO term. Therefore, this file should be regenerated whenever the patient HPO list changes.

The similarity formula used is Lin similarity:

```text
simLin(q, d) = 2 * IC(MICA(q, d)) / (IC(q) + IC(d))
```

Where:

| Symbol | Meaning |
|---|---|
| `q` | Patient/query HPO term |
| `d` | Disease dataset HPO term |
| `IC` | Information content |
| `MICA(q, d)` | Most informative common ancestor of `q` and `d` in the HPO graph |

In this implementation:

- Parent-child relationships are parsed from `is_a` edges in `data/raw/hp.obo`.
- Alternative HPO IDs from `alt_id` are normalized to their primary HPO IDs.
- IC is estimated from the Orphanet disease-HPO baseline itself.
- Disease annotations are propagated to ancestor terms before IC calculation.
- For multiple patient HPOs, the row-level score is the maximum Lin similarity across all patient HPOs.
- Scores are clamped to the range `[0.0, 1.0]`.

Example interpretation:

```text
Patient HPOs:
HP:0001250 Seizure
HP:0001249 Intellectual disability
HP:0000256 Macrocephaly

Row HPO:
HP:0001250 Seizure

hpo_similarity_weight = 1.000000
best_matching_query_hpo = HP:0001250
```

## Processing Scripts

### Extract Baseline CSV From Orphanet XML

Script:

```text
scripts/extract_orphanet_hpo_csv.py
```

Default input:

```text
Orphanet/Clinical_signs_and_symptoms_in_rare_disease.xml
```

Default output:

```text
data/orphanet_clinical_signs_hpo.csv
```

In the current project, the baseline dataset is stored as:

```text
data/processed/HPO_disease_mapping_baseline.csv
```

Example command:

```bash
python3 scripts/extract_orphanet_hpo_csv.py \
  --input Orphanet/Clinical_signs_and_symptoms_in_rare_disease.xml \
  --output data/processed/HPO_disease_mapping_baseline.csv
```

### Add Numeric Frequency Weight

Script:

```text
scripts/add_frequency_weight.py
```

Default input:

```text
data/processed/HPO_disease_mapping_baseline.csv
```

Default output:

```text
data/processed/HPO_disease_mapping_with_frequency_weight.csv
```

Command:

```bash
python3 scripts/add_frequency_weight.py
```

### Add IC Weight

Script:

```text
scripts/add_ic_weight_to_baseline.py
```

Default input:

```text
data/processed/HPO_disease_mapping_baseline.csv
```

Default HPO ontology file:

```text
data/raw/hp.obo
```

Default output:

```text
data/processed/HPO_disease_mapping_baseline_with_ic.csv
```

Command:

```bash
python3 scripts/add_ic_weight_to_baseline.py \
  --baseline_path data/processed/HPO_disease_mapping_baseline.csv \
  --obo_path data/raw/hp.obo \
  --output_path data/processed/HPO_disease_mapping_baseline_with_ic.csv
```

### Add Patient HPO Similarity Weights

Script:

```text
scripts/add_hpo_similarity_weight.py
```

Default input:

```text
data/processed/HPO_disease_mapping_baseline.csv
```

Default HPO ontology file:

```text
data/raw/hp.obo
```

Example command with comma-separated HPO IDs:

```bash
python3 scripts/add_hpo_similarity_weight.py \
  --query-hpo HP:0001250,HP:0001249,HP:0000256 \
  --output data/processed/HPO_disease_mapping_with_patient_similarity.csv
```

Equivalent command with repeated arguments:

```bash
python3 scripts/add_hpo_similarity_weight.py \
  --query-hpo HP:0001250 \
  --query-hpo HP:0001249 \
  --query-hpo HP:0000256 \
  --output data/processed/HPO_disease_mapping_with_patient_similarity.csv
```

## Recommended Use In Disease Ranking

The recommended baseline disease scoring flow is:

```text
Patient HPO list
-> compute row-level HPO graph similarity
-> combine with frequency_weight and ic_weight
-> aggregate row scores by disease_id
-> rank diseases
```

A simple row-level score can be:

```text
row_score = hpo_similarity_weight * frequency_weight * ic_weight
```

Then disease-level scores can be produced by grouping rows by `disease_id` and aggregating `row_score`, for example by sum, mean, max, or a coverage-normalized score.

The best aggregation method has not been finalized in this dataset version. The current files provide the reusable mapping and weight columns needed for downstream disease ranking experiments.

## Version Notes

Current generated dataset version:

```text
Created in project workspace on 2026-07-08
```

Current key outputs:

```text
data/processed/HPO_disease_mapping_baseline.csv
data/processed/HPO_disease_mapping_with_frequency_weight.csv
data/processed/HPO_disease_mapping_baseline_with_ic.csv
data/processed/HPO_disease_mapping_with_patient_similarity.csv
```

The baseline file should be treated as the stable raw processed mapping. Additional weighted files are derived artifacts and can be regenerated from the baseline plus the scripts listed above.
