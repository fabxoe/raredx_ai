# HPO Mapper 사용 가이드

## 1. 무엇을 하는 모듈인가

`hpo_mapper`는 영어 임상 문장 또는 phenotype 표현을 입력받아 유사한 Human Phenotype Ontology(HPO) 용어 후보를 찾는 로컬 Python 모듈이다.

현재 파이프라인은 다음 순서로 동작한다.

```text
Clinical note
-> phenotype phrase 분리
-> phrase별 embedding 생성
-> 미리 생성한 HPO embedding과 cosine similarity 계산
-> threshold 및 Top-K 적용
-> HPO ID 기준 중복 제거
-> 환자 단위 HPO set 생성
```

기본 embedding 모델은 `sentence-transformers/all-MiniLM-L6-v2`이다.

> 이 모듈은 `phenotype text -> HPO` 변환용이다. `HPO -> disease` 질환 랭킹은 별도의 파이프라인이다.

## 2. 현재 폴더 구성

| 파일 | 역할 |
|---|---|
| `hpo_mapper/mapper.py` | 문장/phrase를 HPO 후보로 매핑하고 환자 HPO set을 생성하는 핵심 API |
| `hpo_mapper/parse_hpo.py` | `hp.obo`의 HPO 이름과 동의어를 검색용 CSV로 변환 |
| `hpo_mapper/embed_index.py` | 검색용 텍스트를 embedding하고 로컬 벡터 인덱스 생성 |
| `hpo_mapper/__init__.py` | 외부에서 사용할 공개 함수 노출 |
| `hpo_mapper/HPO_mapper_baseline_history.md` | baseline 설정과 실험 계획 |
| `hpo_mapper/history.md` | 개발 로드맵과 기록 템플릿 |

기본 데이터 경로는 다음과 같다.

| 경로 | 내용 |
|---|---|
| `data/raw/hp.obo` | 원본 HPO ontology |
| `data/processed/hpo_terms.csv` | HPO 이름/동의어 검색 테이블 |
| `data/processed/hpo_terms_index.csv` | embedding 행과 대응되는 메타데이터 |
| `data/processed/hpo_embeddings.npy` | L2 정규화된 HPO embedding 행렬 |

개발 시 사용한 로컬 인덱스는 46,063행, embedding shape은 `(46063, 384)`였다. 데이터와 embedding 파일은 용량 및 데이터 관리 정책에 따라 Git에서 제외될 수 있으므로, clone 후 파일 존재 여부를 확인하고 필요하면 7절의 명령으로 다시 생성한다.

## 3. 실행 준비

프로젝트 루트에서 실행한다.

```bash
git clone https://github.com/fabxoe/raredx_ai.git
cd raredx_ai
uv sync
```

프로젝트의 Python 버전과 의존성은 `pyproject.toml`에 정의되어 있다. `uv`를 사용하지 않는 경우 Python 3.12 이상 환경에서 프로젝트 의존성을 설치한다.

모델이 로컬 cache에 없으면 최초 실행 시 Hugging Face에서 모델을 내려받으므로 인터넷 연결이 필요할 수 있다.

## 4. 가장 간단한 사용법

`data/processed/hpo_terms_index.csv`와 `data/processed/hpo_embeddings.npy`가 준비되어 있다면 인덱스를 다시 만들 필요가 없다. 파일이 없다면 먼저 7절의 인덱스 생성 절차를 실행한다.

### 4.1 짧은 phenotype 표현 하나 매핑

```python
from hpo_mapper import map_text_to_hpo

results = map_text_to_hpo(
    "sensorineural hearing loss",
    top_k=5,
    threshold=0.40,
)

print(results[[
    "rank",
    "hpo_id",
    "hpo_name",
    "matched_text",
    "cosine_score",
]])
```

`map_text_to_hpo()`는 입력 전체를 하나의 query로 취급한다. 이미 정제된 단일 증상 표현을 검색하거나 빠르게 후보를 확인할 때 적합하다.

### 4.2 긴 clinical note에서 여러 phenotype 매핑

```python
from hpo_mapper import (
    aggregate_patient_hpo_set,
    extract_phenotype_phrases,
    map_phrases_to_hpo,
)

note = """
A 12-year-old girl presents with short stature, scoliosis,
sensorineural hearing loss and developmental delay.
"""

phrases = extract_phenotype_phrases(note)
print(phrases)
# ['short stature', 'scoliosis',
#  'sensorineural hearing loss', 'developmental delay']

candidates = map_phrases_to_hpo(
    note,
    top_k_per_phrase=5,
    threshold=0.40,
)

patient_hpo = aggregate_patient_hpo_set(candidates)
print(patient_hpo[["hpo_id", "hpo_name", "cosine_score", "source_phrases"]])
```

긴 note에는 `map_text_to_hpo()`를 직접 적용하기보다 다음 세 단계를 권장한다.

1. `extract_phenotype_phrases()`로 phrase 분리
2. `map_phrases_to_hpo()`로 phrase별 후보 생성
3. `aggregate_patient_hpo_set()`으로 중복 HPO를 합쳐 환자 단위 set 생성

### 4.3 결과를 CSV로 저장

```python
candidates.to_csv("outputs/patient_001_hpo_candidates.csv", index=False)
patient_hpo.to_csv("outputs/patient_001_hpo_set.csv", index=False)
```

`outputs` 폴더가 없는 환경에서는 먼저 생성해야 한다.

## 5. 주요 파라미터

### `map_text_to_hpo()`

| 파라미터 | 기본값 | 설명 |
|---|---:|---|
| `text` | 필수 | 매핑할 영어 phenotype 표현 |
| `top_k` | `10` | threshold 통과 후 반환할 최대 HPO 수 |
| `threshold` | `0.40` | 최소 cosine similarity |
| `deduplicate_hpo` | `True` | 이름/동의어가 같은 HPO ID로 연결되면 최고 점수 결과만 유지 |
| `backend` | `sentence-transformers` | embedding backend. 현재 이 backend만 구현됨 |
| `model_name` | `sentence-transformers/all-MiniLM-L6-v2` | query embedding 모델 |

### `map_phrases_to_hpo()`

| 파라미터 | 기본값 | 설명 |
|---|---:|---|
| `text` | 필수 | 여러 phenotype이 포함될 수 있는 임상 문장 |
| `top_k_per_phrase` | `5` | phrase 하나당 반환할 최대 후보 수 |
| `threshold` | `0.40` | phrase별 최소 cosine similarity |

`model_name`은 반드시 인덱스를 만들 때 사용한 모델과 같아야 한다. 다른 모델을 사용하려면 해당 모델로 인덱스도 다시 생성해야 하며, embedding 차원까지 일치해야 한다.

## 6. 주요 결과 컬럼

| 컬럼 | 의미 |
|---|---|
| `phenotype_phrase` | clinical note에서 분리한 phrase |
| `rank` | 해당 query 또는 phrase 안에서의 후보 순위 |
| `hpo_id`, `hpo_name` | HPO ID와 대표 이름 |
| `matched_text` | 실제로 가장 유사했던 HPO 이름 또는 동의어 |
| `match_type` | `name` 또는 `synonym` |
| `cosine_score` | query와 HPO 검색 텍스트의 cosine similarity |
| `duplicate_count` | 같은 HPO ID로 묶인 검색 행 수 |
| `other_matched_texts` | 같은 HPO ID에서 추가로 매칭된 이름/동의어 |
| `source_phrases` | 최종 환자 HPO에 기여한 원문 phrase 목록 |

`map_phrases_to_hpo()`는 내부에서 이미 threshold 미만 결과를 제거하므로 현재 반환되는 행의 `accepted` 값은 모두 `True`다.

## 7. HPO ontology 또는 모델을 바꿀 때 인덱스 재생성

새 `hp.obo`를 `data/raw/hp.obo`에 둔 뒤 프로젝트 루트에서 실행한다.

```bash
python -m hpo_mapper.parse_hpo
python -m hpo_mapper.embed_index
```

각 단계는 다음 파일을 만든다.

```text
data/raw/hp.obo
-> data/processed/hpo_terms.csv
-> data/processed/hpo_terms_index.csv
   data/processed/hpo_embeddings.npy
```

경로와 모델을 직접 지정할 수도 있다.

```bash
python -m hpo_mapper.parse_hpo \
  --obo_path data/raw/hp.obo \
  --output_path data/processed/hpo_terms.csv

python -m hpo_mapper.embed_index \
  --terms_path data/processed/hpo_terms.csv \
  --index_path data/processed/hpo_terms_index.csv \
  --embeddings_path data/processed/hpo_embeddings.npy \
  --model_name sentence-transformers/all-MiniLM-L6-v2
```

과거 오류 메시지와 문서 일부에는 `python scripts/build_hpo_index.py`가 나오지만 현재 repository에는 그 스크립트가 없다. 위의 `python -m hpo_mapper.parse_hpo`와 `python -m hpo_mapper.embed_index`가 현재 소스에 존재하는 실행 방법이다.

## 8. 현재 구현의 제한사항

- 영어 문장과 영어 HPO 이름/동의어를 전제로 한다.
- phrase 추출은 문장부호, 쉼표, 세미콜론, `and` 등을 이용한 규칙 기반 방식이다.
- negation, family history, historical/temporal context를 아직 구분하지 않는다. 예를 들어 `No developmental delay`도 phenotype 후보로 처리될 수 있다.
- ontology의 ancestor/descendant 관계를 이용한 후보 후처리는 아직 없다.
- `ollama` backend는 인터페이스만 언급되어 있고 실제 구현은 `NotImplementedError`를 발생시킨다.
- embedding 검색은 모든 인덱스 벡터와 직접 내적하므로 대규모 확장 시 별도 vector database 또는 ANN 인덱스가 필요할 수 있다.
- 이 결과는 진단 확정값이 아니라 후보 검색 결과이므로 임상 검토 없이 사용하면 안 된다.

## 9. Plan 관련 문서

현재 프로젝트에는 다음 기획/계획 문서가 있다.

| 문서 | 내용 |
|---|---|
| `docs/hpo_mapper_required_datasets_plan.md` | Combo 2/4/7/9에 필요한 데이터 명세, 준비 상태, 담당자, 단계별 완료 기준 |
| `hpo_mapper/HPO_mapper_baseline_history.md` | baseline 설정, 평가 체크리스트, experiment plan과 기록 템플릿 |
| `hpo_mapper/history.md` | mapper 개발 단계와 평가 데이터셋 준비 체크리스트 |

현재 코드에 구현된 핵심은 multi-phenotype phrase 분리, semantic similarity 검색, Top-K/threshold, HPO ID 중복 제거다. 문서에 계획된 context filtering, ontology-aware filtering, Clinical NER은 아직 `hpo_mapper` 코드에 구현되어 있지 않다.
