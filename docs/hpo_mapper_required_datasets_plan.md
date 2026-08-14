# HPO Mapper Required Datasets Plan

## 1. 목적

이 문서는 HPO Mapper의 단계별 실험에 필요한 데이터와 준비 상태, 담당자, 완료 조건을 관리하기 위한 실행 계획이다.

실험 범위는 다음 네 가지 조합이다.

| 실험 | 구성 | 핵심 검증 항목 |
|---|---|---|
| Combo 2 | A + B + C | Semantic mapping + Top-N + similarity threshold |
| Combo 4 | E-1 + A + B + C + D | Rule-based context filtering 및 similarity weighting |
| Combo 7 | E-2 + A + J + B + C + D | medspaCy context filtering 및 Laboratory-to-HPO mapping |
| Combo 9 | E-2 + A + I + J + B + C + D | Synonym expansion까지 포함한 확장 파이프라인 |

전략 기호의 의미는 다음과 같다.

| 기호 | 전략 |
|---|---|
| A | Basic Semantic HPO Mapping |
| B | Top-N Candidate Mapping |
| C | Similarity Threshold Filtering |
| D | Similarity-based HPO Weighting |
| E-1 | Rule-based Context Filtering |
| E-2 | medspaCy-based Context Filtering |
| I | HPO Synonym Expansion |
| J | Laboratory-to-HPO Mapping |

## 2. 권장 실험 순서

```text
Baseline
-> Combo 2
-> Combo 4
-> Combo 7
-> Combo 9
```

각 단계는 이전 단계의 데이터와 코드를 재사용한다. 다음 단계로 넘어가기 전에 해당 단계의 필수 데이터 검증과 baseline 비교 평가를 완료한다.

## 3. 데이터 의존성 요약

| 데이터 또는 도구 | Combo 2 | Combo 4 | Combo 7 | Combo 9 |
|---|:---:|:---:|:---:|:---:|
| Clinical Note Dataset | 필수 | 필수 | 필수 | 필수 |
| Gold HPO Evaluation Dataset | 필수 | 필수 | 필수 | 필수 |
| HPO Ontology (`hp.obo`) | 필수 | 필수 | 필수 | 필수 |
| HPO Search Index | 필수 | 필수 | 필수 | 필수 |
| HPO Embeddings | 필수 | 필수 | 필수 | 필수 |
| Context Rule Dictionary | - | 필수 | 선택 | 선택 |
| Laboratory Result Dataset | - | - | 필수 | 필수 |
| Reference Range Table | - | - | 필수 | 필수 |
| Laboratory-to-HPO Mapping Table | - | - | 필수 | 필수 |
| medspaCy Context Pipeline | - | - | 필수 | 필수 |
| HPO Synonym Dictionary | - | - | - | 필수 |

## 4. 공통 필수 데이터 명세

### 4.1 Clinical Note Dataset

환자의 임상 서술을 HPO로 변환하기 위한 입력 데이터다.

| 컬럼 | 필수 여부 | 설명 |
|---|:---:|---|
| `patient_id` | 필수 | 환자를 구분하는 고유 ID |
| `clinical_note` | 필수 | Clinical note 원문 |
| `test_results` | 선택 | 검사 결과 원문. Combo 7과 9에서는 필요 |
| `diagnosis` 또는 `Orpha_name` | 선택 | 평가 및 오류 분석용 진단명 |

완료 조건:

- `patient_id`가 비어 있지 않고 평가 단위에서 중복되지 않는다.
- `clinical_note`가 비어 있는 행을 제거하거나 별도로 표시한다.
- 실제 환자 데이터라면 비식별화 여부를 확인한다.
- 입력 encoding과 줄바꿈 규칙을 통일한다.

### 4.2 HPO Ontology

기본 파일:

```text
data/raw/hp.obo
```

사용 목적:

- HPO ID와 대표 이름 조회
- HPO synonym 및 definition 추출
- obsolete term 제외 또는 대체 ID 처리
- 향후 ontology 구조 기반 후처리

완료 조건:

- 사용한 HPO release 또는 다운로드 날짜를 기록한다.
- 파싱 후 HPO ID, 이름, synonym이 정상적으로 생성되는지 확인한다.
- obsolete term 처리 정책을 명시한다.

### 4.3 HPO Search Index

현재 mapper는 HPO 이름과 synonym을 각각 검색 가능한 행으로 확장한다.

현재 구현의 필수 컬럼:

| 컬럼 | 설명 |
|---|---|
| `hpo_id` | HPO ID |
| `hpo_name` | HPO 대표 이름 |
| `matched_text` | embedding 대상인 대표 이름 또는 synonym |
| `match_type` | `name` 또는 `synonym` |
| `definition` | HPO definition |
| `is_obsolete` | obsolete 여부 |
| `model_name` | index 생성에 사용한 embedding 모델 |

> 원문의 `synonyms` 단일 컬럼 대신, 현재 코드는 synonym 하나를 `matched_text` 한 행으로 저장한다.

완료 조건:

- index 행 수와 embedding 행 수가 일치한다.
- 모든 검색 행에 `hpo_id`, `hpo_name`, `matched_text`가 존재한다.
- index의 `model_name`과 query embedding 모델이 동일하다.

### 4.4 HPO Embeddings

기본 파일:

```text
data/processed/hpo_embeddings.npy
```

현재 구현은 HPO 이름과 synonym을 embedding한다. Definition을 embedding에 포함하려면 index 생성 로직과 평가 조건을 별도로 변경해야 한다.

완료 조건:

- embedding shape의 첫 번째 차원이 index 행 수와 같다.
- 모든 벡터가 동일한 모델과 설정으로 생성된다.
- query와 index embedding 차원이 일치한다.
- 모델명과 생성 날짜를 기록한다.

### 4.5 Gold HPO Evaluation Dataset

모든 실험 조합을 같은 기준으로 비교하기 위한 정답 데이터다.

| 컬럼 | 필수 여부 | 설명 |
|---|:---:|---|
| `patient_id` | 필수 | Clinical Note Dataset과 연결되는 ID |
| `clinical_note` | 권장 | 평가 대상 원문 |
| `gold_hpo_ids` | 필수 | 정답 HPO ID 목록 |
| `dataset_split` | 권장 | A/B 또는 train/dev/test 구분 |
| `family_history` | 선택 | context 평가용 annotation |
| `historical` | 선택 | context 평가용 annotation |
| `uncertain` | 선택 | context 평가용 annotation |

권장 최소 규모는 수작업 annotation 30~50건이며, 가능하면 100건을 두 명 이상이 분담하고 일부 표본을 교차 검수한다.

평가 지표:

- Precision
- Recall
- F1 score
- Top-K accuracy
- 필요 시 exact match와 ancestor/descendant match를 분리한 오류 분석

완료 조건:

- `gold_hpo_ids`의 구분자와 형식이 통일되어 있다.
- 모든 HPO ID가 사용 중인 `hp.obo`에서 유효하다.
- annotation 지침과 애매한 사례의 처리 원칙이 문서화되어 있다.
- 빈 정답 행, 중복 ID, 잘못된 ID를 자동 검사한다.

## 5. 조합별 추가 데이터

### 5.1 Combo 4: Context Rule Dictionary

Rule-based context detection에 사용한다.

대상 label:

- `present`
- `negated`
- `family_history`
- `historical`
- `uncertain`

초기 dictionary 예시:

```yaml
negated:
  - no
  - denied
  - without

family_history:
  - family history of

historical:
  - previous
  - resolved

uncertain:
  - possible
  - suspected
```

완료 조건:

- label별 trigger와 termination rule을 정의한다.
- 대소문자, 문장 경계, 적용 범위를 테스트한다.
- context별 positive/negative 예제로 unit test를 작성한다.
- Combo 7에서 medspaCy로 대체하더라도 Combo 4 baseline 재현을 위해 dictionary를 보존한다.

### 5.2 Combo 7: Laboratory Result Dataset

| 컬럼 | 필수 여부 | 설명 |
|---|:---:|---|
| `patient_id` | 필수 | 환자 ID |
| `test_results` | 필수 | 검사 결과 원문 |

예시:

```text
TSH < 0.003
IgG4 = 312 mg/dL
```

완료 조건:

- 최소한 검사명, 비교 연산자, 수치, 단위를 파싱할 수 있다.
- 파싱 실패와 단위 누락 사례를 별도 기록한다.
- Clinical Note Dataset의 `patient_id`와 연결된다.

### 5.3 Combo 7: Reference Range Table

| 컬럼 | 필수 여부 | 설명 |
|---|:---:|---|
| `lab_name` | 필수 | 표준화된 검사명 |
| `lower` | 필수 | 정상 하한 |
| `upper` | 필수 | 정상 상한 |
| `unit` | 필수 | 기준 단위 |
| `sex` | 선택 | 성별에 따른 기준 차이 |
| `age_min`, `age_max` | 선택 | 연령에 따른 기준 차이 |

담당자: 가빈

완료 조건:

- 동일 검사명의 별칭을 표준 이름으로 정규화한다.
- 단위 변환 정책을 정한다.
- 성별 및 연령별 reference range가 필요한 검사를 표시한다.
- 경계값이 정상에 포함되는지 규칙을 명시한다.

### 5.4 Combo 7: Laboratory-to-HPO Mapping Table

| 컬럼 | 필수 여부 | 설명 |
|---|:---:|---|
| `lab_name` | 필수 | 표준화된 검사명 |
| `condition` | 필수 | `low`, `high`, `abnormal` 등 |
| `hpo_id` | 필수 | 대응 HPO ID |
| `hpo_name` | 필수 | 대응 HPO 이름 |

예시:

| lab_name | condition | hpo_id | hpo_name |
|---|---|---|---|
| C-reactive protein | high | HP:0011227 | Elevated circulating C-reactive protein concentration |

담당자: 성민

완료 조건:

- 하나의 검사/상태가 여러 HPO에 대응할 때의 정책을 정한다.
- 모든 HPO ID를 `hp.obo`로 검증한다.
- 모순되는 매핑과 빈 ID를 검사한다.
- `high hemoglobin -> anemia`와 같이 임상적으로 모순될 수 있는 예시는 전문가 검수 후 확정한다.

### 5.5 Combo 7: medspaCy Context Pipeline

적용 대상:

- Negation
- Family history
- Historical
- Uncertain

완료 조건:

- 설치 버전과 language model 또는 rule 설정을 고정한다.
- phrase 단위 context label을 mapper 출력에 보존한다.
- Combo 4 rule-based 결과와 동일 평가셋으로 비교한다.
- 적용 범위와 termination rule 오류를 분석한다.

### 5.6 Combo 9: HPO Synonym Dictionary

가능하면 `hp.obo`에서 자동 생성한다.

```text
hearing loss
hearing impairment
hearing deficit
-> HP:0000365
```

완료 조건:

- synonym과 대표 HPO ID의 연결이 유지된다.
- 대소문자만 다른 중복과 완전히 같은 synonym을 정리한다.
- 하나의 synonym이 여러 HPO ID에 연결되는 ambiguity를 기록한다.
- 현재 HPO index에 이미 포함된 synonym과 중복 구현하지 않는지 확인한다.

> 현재 mapper의 HPO index는 `hp.obo`의 synonym을 이미 검색 행으로 포함한다. 따라서 Combo 9에서는 별도 dictionary를 만들기 전에 추가 synonym expansion이 실제로 recall을 높이는지 확인해야 한다.

## 6. 현재 프로젝트에서 확인된 준비 상태

상태 기준:

- **확인됨**: 파일과 기본 schema를 로컬에서 확인함
- **부분 준비**: 파일은 있으나 annotation, 구현 또는 품질 검수가 남음
- **미확인**: 사용 가능한 최종 산출물을 현재 프로젝트에서 확인하지 못함

| 항목 | 상태 | 확인 경로 또는 메모 | 담당자 |
|---|---|---|---|
| Clinical Note Dataset | 확인됨 | `data/processed/rarearena_rdc_sample_1000.csv`; `patient_id`, `clinical_note`, `test_results` 존재 | - |
| HPO Ontology | 확인됨 | `data/raw/hp.obo` | - |
| HPO Search Index | 확인됨 | `data/processed/hpo_terms.csv`, `data/processed/hpo_terms_index.csv` | - |
| HPO Embeddings | 확인됨 | `data/processed/hpo_embeddings.npy`; index와 46,063행 일치 | - |
| Gold HPO Evaluation Dataset | 부분 준비 | master 100건 및 A/B 각 50건은 있으나 `gold_hpo_ids`가 아직 모두 비어 있음 | 고은, 현우 |
| Context Rule Dictionary | 미확인 | 계획 문서의 예시만 존재하며 실행용 dictionary 파일은 확인되지 않음 | 미정 |
| Laboratory Result Dataset | 부분 준비 | Clinical Note Dataset에 `test_results` 컬럼 존재; 파싱 가능성과 품질 검수 필요 | - |
| Reference Range Table | 부분 준비 | `data/Reference Range Table.xlsx`, `Private & Shared/Laboratory-to-HPO Mapping Table/reference_range_table_extension_final.csv` | 가빈 |
| Laboratory-to-HPO Mapping Table | 부분 준비 | `Private & Shared/Laboratory-to-HPO Mapping Table 3aa52d7787fa80dbafc0df22b80922c5.md`에 초안 매핑이 있으나 실행용 최종 CSV와 임상 검수가 필요 | 성민 |
| medspaCy Context Pipeline | 미확인 | 현재 `hpo_mapper` Python 코드에서 구현을 확인하지 못함 | 미정 |
| HPO Synonym Dictionary | 확인됨 | `hp.obo`에서 추출되어 현재 HPO index의 `matched_text`/`match_type`에 포함됨 | - |

## 7. 단계별 실행 계획

### Phase 0: 공통 데이터 검증

- [ ] Clinical Note Dataset의 빈 값과 중복 환자 검사
- [ ] HPO ontology release 정보 기록
- [ ] HPO index와 embedding 일관성 검사 자동화
- [ ] Gold annotation 지침 확정
- [ ] `gold_hpo_ids` 입력 및 교차 검수

완료 기준: Combo 2를 동일 입력과 정답으로 반복 평가할 수 있다.

### Phase 1: Combo 2

- [ ] phrase별 Top-N 후보 생성
- [ ] threshold 후보군 비교
- [ ] Precision, Recall, F1, Top-K accuracy 측정
- [ ] threshold와 Top-N 값을 실험 기록에 고정

완료 기준: Baseline 대비 Combo 2 결과와 오류 유형이 기록되어 있다.

### Phase 2: Combo 4

- [ ] Context Rule Dictionary 작성
- [ ] negated/family history/historical/uncertain 처리 구현
- [ ] similarity score 보존 및 weighting 출력 정의
- [ ] Combo 2와 동일 평가셋으로 비교

완료 기준: context filtering의 precision/recall 변화와 대표 오류가 기록되어 있다.

### Phase 3: Combo 7

- [ ] Laboratory Result Dataset 파싱 규칙 확정
- [ ] Reference Range Table 정규화
- [ ] Laboratory-to-HPO Mapping Table 검수
- [ ] medspaCy context pipeline 구현 및 버전 고정
- [ ] text-derived HPO와 lab-derived HPO의 provenance 보존

완료 기준: lab 결과가 환자별 HPO로 재현 가능하게 변환되고 Combo 4와 비교 평가된다.

### Phase 4: Combo 9

- [ ] 현재 HPO index synonym coverage 측정
- [ ] 추가 synonym source와 충돌 처리 정책 결정
- [ ] synonym expansion 적용 전후 recall 비교
- [ ] 전체 파이프라인 ablation 결과 정리

완료 기준: synonym expansion의 추가 효과가 수치로 확인되고 최종 조합 채택 여부가 결정된다.

## 8. 실험 공통 산출물

각 실험은 최소한 다음 파일 또는 기록을 남긴다.

- 실행 설정: 데이터 버전, 모델명, Top-N, threshold, context 방식
- 환자별 phrase 및 context label
- phrase별 HPO 후보, rank, similarity score
- 최종 선택된 환자 HPO set과 출처(`clinical_note` 또는 `lab`)
- 전체 평가 지표
- 실패 사례 및 오류 유형
- 이전 단계 대비 변경점과 결론

권장 결과 schema:

| 컬럼 | 설명 |
|---|---|
| `patient_id` | 환자 ID |
| `source_type` | `clinical_note` 또는 `lab` |
| `original_text` | 원문 phrase 또는 검사 결과 |
| `cleaned_phrase` | 정제된 phenotype phrase |
| `context_label` | present/negated/family_history/historical/uncertain |
| `candidate_hpo_id` | 후보 HPO ID |
| `candidate_hpo_name` | 후보 HPO 이름 |
| `similarity_score` | cosine similarity |
| `rank` | phrase 내 후보 순위 |
| `final_selected` | 최종 선택 여부 |

## 9. 우선 작업

현재 가장 큰 blocker는 Gold HPO Evaluation Dataset의 정답 annotation이 비어 있다는 점이다. 다음 순서로 진행한다.

1. Gold annotation 지침과 HPO ID 구분자 확정
2. 고은·현우 담당 A/B set annotation
3. 일부 표본 교차 검수 및 HPO ID 유효성 검사
4. Combo 2 baseline 평가
5. Context Rule Dictionary 작성 후 Combo 4 진행
6. Lab 관련 표준화와 medspaCy 구현 후 Combo 7 진행
7. 기존 synonym index의 효과를 검증한 뒤 Combo 9 진행
