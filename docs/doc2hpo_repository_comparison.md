# Doc2HPO/HPO Mapper 계열 저장소 알고리즘 비교

이 문서는 RARE_DX_AI 프로젝트에서 참고 중인 두 HPO 관련 저장소의 역할과 알고리즘 차이를 정리한 것이다.

비교 대상:

- `phenotype_embedding`: https://github.com/maryamdaniali/phenotype_embedding
- `UoS-HGIG/HPO-Mapper`: https://github.com/UoS-HGIG/HPO-Mapper

## 핵심 요약

두 저장소는 모두 HPO와 embedding을 사용하지만, 해결하려는 문제가 다르다.

- `phenotype_embedding`은 HPO ontology graph 안에서 HPO term 자체의 vector representation을 학습한다.
- `HPO-Mapper`는 clinical finding text를 표준 HPO term으로 매핑한다.

즉, 두 저장소는 경쟁 관계라기보다 파이프라인의 서로 다른 위치에 있다.

```text
HPO-Mapper:
clinical note -> HPO terms

phenotype_embedding:
HPO terms -> graph-aware HPO vectors -> similarity/ranking
```

## 알고리즘 차이 표

| 비교 항목 | `phenotype_embedding` | `UoS-HGIG/HPO-Mapper` |
|---|---|---|
| 핵심 목적 | HPO ontology graph의 각 HPO node를 vector로 학습 | clinical finding text를 표준 HPO term으로 매핑 |
| 문제 정의 | `HPO term`과 `HPO term` 사이의 유사도 학습 | `free text / finding`과 `HPO term` 사이의 매핑 |
| 입력 | HPO DAG, HPO term frequency table | finding, anatomical region, HPO synonym embedding DB |
| 출력 | HPO node embedding vector | HPO ID, HPO term, matched synonym, score, associated genes |
| 알고리즘 계열 | Graph representation learning | Semantic retrieval / phenotype normalization |
| 주요 모델 | Node2Vec / Node2Vec+ | Embedding cosine similarity + optional LLM |
| 그래프 사용 여부 | 강하게 사용한다. HPO `IS_A` DAG 위에서 random walk 수행 | 직접 graph walk를 하지는 않는다. HPO term/synonym embedding DB를 검색 |
| edge weight 의미 | HPO DAG random walk 확률을 조정하는 값 | edge weight 개념은 핵심이 아니다 |
| edge weight 계산 | `default_weight + min(parent.prob_descendants, child.prob_descendants)` | 해당 없음 |
| frequency 사용 | clinical note corpus에서 phenotype frequency를 계산해 HPO node probability로 반영 | 기본 알고리즘은 text embedding similarity 중심 |
| embedding 생성 방식 | HPO graph random walk -> skip-gram 학습 -> HPO node vector 생성 | query text와 HPO synonym term을 embedding model로 vector화 |
| similarity 계산 | 학습된 HPO node embedding 간 cosine similarity | query embedding과 HPO synonym embedding 간 cosine similarity |
| LLM 사용 | 없음 | Protocol 2/3에서 선택적으로 사용 |
| Protocol 구분 | weight system: `equal`, `random`, `probabilistic`, `probabilistic_with_bias`; Node2Vec/Node2Vec+ | P1: embedding only, P2: embedding + LLM QC, P3: embedding top-k + LLM selection |
| 학습 필요 여부 | 필요하다. Node2Vec skip-gram 학습을 수행한다 | 보통 사전계산된 embedding DB를 사용하고, 입력 query embedding만 계산한다 |
| clinical note 직접 처리 | 직접 처리하지 않는다. note corpus는 frequency table 생성에 사용된다 | 직접 처리한다. finding + region을 HPO로 변환한다 |
| gene 연결 | 주요 목적은 아니다 | HPO term에 associated genes를 붙여 출력한다 |
| RARE_DX_AI에서의 위치 | Baseline 3: HPO graph embedding + FAISS 후보 | Baseline 4: clinical note-to-HPO mapper 후보 |
| disease ranking에 쓰는 방법 | HPO vector를 평균내 patient/disease vector를 만들고 FAISS 검색 가능 | note를 HPO term으로 바꾼 뒤, 기존 IC/SapBERT/Neo4j ranking pipeline에 입력 |
| 장점 | ontology 구조와 phenotype frequency를 embedding에 반영 | 실제 임상 표현을 HPO로 바꾸는 앞단 문제에 직접 대응 |
| 한계 | free text를 HPO로 바로 바꾸지는 못한다 | HPO graph 구조나 IC semantic similarity를 직접 학습하지는 않는다 |

## `phenotype_embedding` 알고리즘

`phenotype_embedding`은 HPO ontology를 graph로 보고, HPO node embedding을 학습한다.

흐름:

```text
HPO DAG
-> node frequency / propagated frequency 계산
-> edge weight 부여
-> weighted random walk
-> positive/negative pair 생성
-> skip-gram 학습
-> HPO term embedding 생성
```

핵심은 HPO `IS_A` 구조를 따라 random walk를 만들고, 그 walk에서 자주 함께 등장하는 HPO term들이 embedding 공간에서 가까워지도록 학습하는 것이다.

edge weight는 다음 의미를 가진다.

```text
edge(parent, child)의 weight
= default_weight + min(parent.prob_descendants, child.prob_descendants)
```

여기서 `prob_descendants`는 해당 HPO term과 그 하위 phenotype까지 반영한 propagated probability다.

따라서 이 weight는 disease ranking score가 아니라, Node2Vec random walk가 HPO graph 위에서 어느 edge를 더 자주 따라갈지 정하는 확률적 가중치다.

## `HPO-Mapper` 알고리즘

`HPO-Mapper`는 clinical finding text를 HPO term으로 mapping하는 도구다.

흐름:

```text
clinical finding + anatomical region
-> query embedding
-> HPO synonym embedding DB 검색
-> cosine similarity 기준 top candidate 선택
-> optional LLM QC 또는 LLM selection
-> HPO ID, HPO term, gene annotation 출력
```

Protocol은 세 단계로 나뉜다.

| Protocol | 설명 | 특징 |
|---|---|---|
| Protocol 1 | Embedding-based mapping | LLM 없이 cosine similarity로 HPO term 선택 |
| Protocol 2 | Embedding retrieval + LLM quality control | embedding으로 선택한 mapping이 잘못됐는지 LLM이 flag |
| Protocol 3 | Embedding retrieval + LLM-based HPO selection | top-k 후보를 LLM에 보여주고 가장 적절한 HPO term을 선택 |

이 도구의 핵심은 HPO graph learning이 아니라 phenotype normalization이다.

예:

```text
"episodes of convulsions"
-> semantic retrieval
-> HP:0001250 Seizure
```

dictionary matcher라면 `"seizure"`라는 단어가 직접 등장하지 않으면 놓칠 수 있지만, HPO-Mapper 방식은 embedding similarity를 이용해 더 유연하게 매핑할 수 있다.

## RARE_DX_AI에서의 적용 위치

현재 RARE_DX_AI pipeline은 다음 흐름을 기준으로 한다.

```text
HPO terms
-> IC baseline
-> SapBERT + FAISS disease retrieval
-> Neo4j graph evidence
-> hybrid re-ranking
```

두 저장소를 적용하면 역할이 다르다.

### `HPO-Mapper` 적용 위치

```text
clinical note
-> HPO-Mapper
-> HPO terms
-> RARE_DX_AI ranking pipeline
```

즉, clinical note 입력을 HPO term으로 바꾸는 앞단 모듈이다.

### `phenotype_embedding` 적용 위치

```text
HPO ontology
-> HPO graph embedding 학습
-> patient HPO vector / disease HPO vector 생성
-> FAISS similarity search
```

즉, HPO term이 이미 주어졌을 때 graph-aware embedding baseline으로 사용할 수 있다.

## Baseline 분류

RARE_DX_AI의 baseline은 다음처럼 나누는 것이 적절하다.

```text
Baseline 1: IC-weighted HPO overlap
Baseline 2: SapBERT disease embedding + FAISS
Baseline 3: phenotype_embedding 방식의 HPO graph embedding + FAISS
Baseline 4: HPO-Mapper 방식의 clinical note-to-HPO mapper
```

평가 기준은 분리해야 한다.

- Baseline 1~3은 gold HPO term이 주어졌을 때 disease candidate ranking을 평가한다.
- Baseline 4는 clinical note에서 HPO term을 얼마나 정확히 추출하고 정규화하는지 평가한다.
- 이후 Baseline 4의 출력 HPO를 ranking pipeline에 넣어 end-to-end 성능을 별도로 확인한다.

## 결론

`phenotype_embedding`과 `HPO-Mapper`는 모두 HPO 기반 embedding을 다루지만 목적이 다르다.

- `phenotype_embedding`: HPO graph 구조를 학습해 HPO term vector를 만든다.
- `HPO-Mapper`: clinical text를 HPO term으로 변환한다.

따라서 RARE_DX_AI에서는 둘을 같은 baseline으로 묶기보다, 하나는 graph embedding retrieval baseline, 다른 하나는 clinical note-to-HPO mapping baseline으로 분리해서 실험하는 것이 적절하다.
