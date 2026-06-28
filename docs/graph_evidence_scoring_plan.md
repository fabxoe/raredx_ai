# Graph Evidence Scoring 설계 플랜

작성일: 2026-06-28

## 배경

현재 RARE_DX_AI의 disease ranking은 다음 세 축으로 구성되어 있다.

- `IC`: 환자 HPO와 disease-HPO annotation의 겹침을 정보량으로 가중한다.
- `Embedding`: 환자 phenotype profile과 disease phenotype profile의 벡터 유사도를 계산한다.
- `Graph evidence`: Neo4j에 적재된 Disease-Gene-Phenotype 관계를 근거로 후보 질환을 보강한다.

현재 graph score는 `local_overlap`에 가깝다.

```text
graph_score = matched patient HPO count / input patient HPO count
```

이 방식은 직관적이고 빠르지만, IC baseline과 같은 `환자 HPO ∩ 질환 HPO` 신호를 많이 공유한다. 따라서 hybrid ranking에서 `IC score`와 `local_overlap graph score`를 동시에 크게 반영하면 같은 근거를 중복 적용할 위험이 있다.

## 핵심 판단

`Graph only` ranking은 연구용 비교군으로는 남길 수 있지만, 현재 `local_overlap`만으로는 많은 후보가 모두 1.0이 되어 구분력이 약하다.

따라서 v1.5에서는 graph를 독립 ranking mode의 주력으로 밀기보다, `Hybrid` 내부의 설명 가능한 evidence component로 강화하는 편이 적절하다.

권장 UI 구조:

```text
Disease ranking
- IC
- Embedding
- Hybrid

Hybrid 내부 옵션
- Disease embedding backend
- IC weight
- Embedding weight
- Graph weight
- Graph evidence mode
```

`Graph only`는 아래 조건을 만족할 때 다시 독립 탭으로 올리는 것이 좋다.

- graph score가 단순 HPO overlap을 넘어선다.
- 후보 간 score 분포가 충분히 갈린다.
- Evidence panel에서 왜 graph score가 높았는지 path 단위로 설명 가능하다.

## Graph Evidence Mode 후보

### 1. local_overlap

현재 단순 baseline이다.

정의:

```text
local_overlap(disease) =
  count(patient_hpo ∩ disease_hpo) / count(patient_hpo)
```

장점:

- 빠르다.
- 구현과 설명이 쉽다.
- Neo4j graph가 없어도 processed KB만으로 계산 가능하다.

한계:

- IC와 중복이 크다.
- broad phenotype과 rare phenotype의 차이를 반영하지 못한다.
- 세 HPO가 모두 맞으면 많은 질환이 1.0으로 묶인다.

권장 역할:

- baseline/debug 용도
- graph evidence pipeline이 정상 동작하는지 확인하는 최소 기능

### 2. gene_path

Disease-Gene-Phenotype 경로를 이용해 후보 질환의 유전적 근거를 보강한다.

예시 경로:

```text
Patient
  -> Phenotype(HP:0001250, Seizure)
  -> Disease(OMIM:...)
  -> Gene(Gene symbol)
  -> Phenotype(other associated phenotype)
```

가능한 scoring:

```text
gene_path_score(disease) =
  normalized count of supporting genes connected to matched phenotypes
```

또는:

```text
gene_path_score(disease) =
  count(unique genes supporting matched HPOs for this disease)
  / count(unique genes associated with this disease)
```

장점:

- IC와 다른 신호를 제공한다.
- phenotype만 겹치는 질환과, phenotype-gene 연결까지 지지되는 질환을 구분할 수 있다.
- Evidence panel에서 `Disease -> Gene -> Phenotype` path를 보여주기 좋다.

한계:

- gene annotation이 많은 질환이 유리해질 수 있다.
- gene coverage가 낮은 질환은 불리해질 수 있다.
- score normalization이 필요하다.

권장 역할:

- Hybrid graph component의 주요 후보
- 후보 질환의 associated gene 설명 강화

### 3. frequency_weighted_graph

HPO annotation의 disease-specific frequency를 graph score에 반영한다.

직관:

같은 phenotype이 질환에 연결되어 있어도, 그 phenotype이 해당 질환에서 자주 나타나는지 드물게 나타나는지는 다르다.

예:

```text
Disease A - HAS_PHENOTYPE {frequency: "Frequent"} -> Seizure
Disease B - HAS_PHENOTYPE {frequency: "Very rare"} -> Seizure
```

가능한 scoring:

```text
frequency_weighted_graph(disease) =
  sum(frequency_weight(h) for h in matched patient HPOs)
  / max_possible_frequency_sum
```

예시 frequency weight:

```text
Obligate / 100%        -> 1.00
Very frequent          -> 0.90
Frequent               -> 0.75
Occasional             -> 0.40
Very rare              -> 0.15
Unknown or missing     -> 0.30
```

장점:

- 단순 overlap보다 질환별 phenotype 중요도를 더 잘 반영한다.
- IC와 다르다. IC는 전체 질환군에서 phenotype이 얼마나 희귀한지를 보고, frequency는 특정 질환 안에서 그 phenotype이 얼마나 전형적인지를 본다.
- hybrid에서 중복 위험이 local_overlap보다 낮다.

한계:

- `phenotype.hpoa`의 frequency 값이 모두 채워져 있지는 않다.
- frequency 표현이 범주형/문자열/비율 등으로 섞일 수 있어 정규화가 필요하다.
- 결측값 처리 정책이 필요하다.

권장 역할:

- v1.5에서 가장 먼저 구현할 graph evidence mode
- `local_overlap`보다 실질적인 개선 가능성이 높다.

### 4. source_confidence_graph

Annotation source, evidence, provenance 정보를 바탕으로 graph evidence 신뢰도를 보정한다.

가능한 scoring:

```text
source_confidence_graph(disease) =
  sum(confidence_weight(annotation.source, annotation.evidence))
  / matched_annotation_count
```

장점:

- 같은 edge라도 근거의 품질을 구분할 수 있다.
- 추후 curated source와 자동 생성 source를 함께 사용할 때 중요하다.
- 연구/서비스에서 evidence quality를 설명하기 좋다.

한계:

- 현재 HPO annotation 파일의 source/evidence 필드가 충분히 세밀하지 않을 수 있다.
- source별 confidence weight는 연구팀 합의가 필요하다.
- 과도하게 임의적인 weight를 넣으면 재현성이 떨어진다.

권장 역할:

- frequency 기반 graph score 이후 추가
- annotation 품질 관리와 함께 진행

### 5. ontology_path_graph

HPO ontology의 parent-child 구조를 사용해 직접 일치하지 않는 phenotype도 의미적으로 연결한다.

예:

```text
Patient: HP:0001250 Seizure
Disease: HP:0012638 Abnormal nervous system physiology
```

직접 같은 HPO ID가 아니더라도 ancestor/descendant 관계를 통해 부분 점수를 줄 수 있다.

가능한 scoring:

```text
ontology_path_graph(patient_hpo, disease_hpo) =
  similarity based on shortest path, shared ancestors, or IC-weighted semantic similarity
```

장점:

- Phenomizer류 semantic similarity에 가까운 방향으로 확장 가능하다.
- clinical note mapper가 조금 더 넓은 HPO term을 뽑아도 후보 검색이 가능해진다.
- HPO 계층 구조를 실제로 활용한다.

한계:

- IC semantic similarity와 중복될 수 있다.
- 단순 path length만 쓰면 ontology 깊이 차이 때문에 왜곡될 수 있다.
- 제대로 하려면 Resnik, Lin, Jiang-Conrath 등 semantic similarity 기준을 정해야 한다.

권장 역할:

- v1.5 이후
- IC baseline을 고도화하거나 graph evidence와 분리해 실험

## IC와 Graph의 중복 문제

중복 위험이 높은 조합:

```text
Hybrid = IC score + local_overlap graph score + embedding score
```

이유:

- `IC score`도 환자 HPO와 질환 HPO의 overlap을 기반으로 한다.
- `local_overlap graph score`도 같은 overlap을 기반으로 한다.
- 차이는 IC weight 적용 여부뿐이라 같은 근거를 두 번 세는 효과가 생길 수 있다.

중복을 줄이는 권장 조합:

```text
Hybrid = IC score
       + embedding score
       + graph evidence score
```

여기서 graph evidence score는 가능한 한 다음 요소를 사용한다.

- disease-specific frequency
- gene path support
- source confidence

즉, graph score는 단순히 “같은 HPO가 몇 개 겹쳤는가”가 아니라 “그 HPO 연결이 graph 안에서 얼마나 강한 근거를 갖는가”를 표현해야 한다.

## 권장 구현 순서

### Step 1. 현재 local_overlap을 baseline으로 명시

목표:

- 현재 graph score가 단순 overlap baseline임을 코드와 문서에 명확히 남긴다.
- UI에서는 `local_overlap`을 실험용 graph evidence mode로 표시한다.

할 일:

- Graph evidence mode 설명 tooltip 추가
- Evidence panel에서 `Not used` 표시 유지
- `local_overlap`은 IC와 중복 가능성이 있음을 문서화

### Step 2. frequency_weighted_graph 구현

목표:

- `phenotype.hpoa`에서 온 frequency 정보를 graph score에 반영한다.

할 일:

- frequency 문자열/비율 parsing 함수 추가
- `DiseasePhenotype` processed schema에 frequency normalization 필드 추가 여부 검토
- graph score 계산 함수 추가
- fixture test 작성

예상 응답 component:

```json
{
  "score_components": {
    "ic": 0.72,
    "embedding": 0.64,
    "graph": 0.81,
    "graph_mode": "frequency_weighted_graph"
  }
}
```

### Step 3. gene_path score 구현

목표:

- disease-gene-phenotype 연결을 evidence로 활용한다.

할 일:

- Neo4j 또는 processed KB에서 disease-gene-phenotype support 계산
- broad gene list가 너무 클 때 preview limit과 full count를 분리
- Evidence panel에서 gene path를 구조적으로 표시

주의:

- gene 수가 많은 질환이 무조건 유리해지지 않도록 normalization 필요

### Step 4. source_confidence_graph 구현

목표:

- source/evidence 기반 신뢰도 보정.

할 일:

- HPO annotation source/evidence 필드 현황 조사
- source confidence weight table 정의
- 결측값 처리 정책 정의
- audit 가능한 설정 파일로 관리

### Step 5. ontology_path_graph 실험

목표:

- HPO ancestor/descendant 관계를 활용한 semantic similarity 확장.

할 일:

- HPO ontology graph를 processed KB에 명시적으로 저장
- direct match, ancestor match, descendant match를 구분
- IC semantic similarity와 중복 여부 평가

## UI 반영 방향

현재 추천:

```text
Disease ranking
- IC
- Embedding
- Hybrid
```

Hybrid 선택 시:

```text
IC weight
Embedding weight
Graph weight
Graph evidence mode
  - local_overlap
  - frequency_weighted_graph
  - gene_path
  - source_confidence_graph
```

Graph evidence mode 설명은 tooltip 또는 help panel로 제공한다.

`Graph only`는 당장은 숨기거나 연구자 옵션으로 낮은 우선순위에 둔다.

## 평가 계획

각 mode는 다음 기준으로 비교한다.

- Top-k accuracy
- MRR
- 후보 score 분포
- IC 대비 ranking 변화
- rarearena clinical note sample에서 Orpha ID coverage
- failure case에서 설명 가능성

중요:

score가 높아졌다는 것만으로 좋은 모델이라고 판단하지 않는다. 후보 순위가 임상적으로 해석 가능한 방향으로 바뀌었는지, 어떤 evidence 때문에 바뀌었는지 함께 확인해야 한다.

## 결론

현재 graph score는 단순 overlap baseline이므로 독립 ranking mode로는 구분력이 약하다. v1.5에서는 `Hybrid` 안의 graph evidence component를 강화하고, `frequency_weighted_graph`, `gene_path`, `source_confidence_graph` 순으로 구현하는 것이 가장 실용적이다.

GNN은 이 baseline들이 정리된 뒤, graph evidence가 실제로 어떤 failure case를 해결하지 못하는지 확인한 다음 성능 향상 실험으로 들어가는 편이 적절하다.
