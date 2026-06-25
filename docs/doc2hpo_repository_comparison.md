# Doc2HPO/HPO Mapper 계열 저장소 알고리즘 비교

이 문서는 RARE_DX_AI 프로젝트에서 참고 중인 두 HPO 관련 저장소와 현재 RARE_DX_AI 서비스에 적용된 알고리즘의 역할과 차이를 정리한 것이다.

비교 대상:

- `phenotype_embedding`: https://github.com/maryamdaniali/phenotype_embedding
- `UoS-HGIG/HPO-Mapper`: https://github.com/UoS-HGIG/HPO-Mapper
- 현재 RARE_DX_AI 서비스 구현

## 핵심 요약

세 방식은 모두 HPO와 embedding을 사용하지만, 해결하려는 문제가 다르다.

- `phenotype_embedding`은 HPO ontology graph 안에서 HPO term 자체의 vector representation을 학습한다.
- `HPO-Mapper`는 clinical finding text를 표준 HPO term으로 매핑한다.
- 현재 RARE_DX_AI는 이미 주어진 HPO term 또는 dictionary matcher로 추출한 HPO term을 이용해 disease candidate ranking과 graph evidence를 제공한다.

즉, 세 방식은 경쟁 관계라기보다 파이프라인의 서로 다른 위치에 있다.

```text
HPO-Mapper:
clinical note -> HPO terms

phenotype_embedding:
HPO terms -> graph-aware HPO vectors -> similarity/ranking

현재 RARE_DX_AI:
HPO terms 또는 dictionary-extracted HPO terms
-> IC baseline + SapBERT/FAISS + Neo4j graph evidence
-> hybrid disease ranking
```

## 알고리즘 차이 표

| 비교 항목 | `phenotype_embedding` | `UoS-HGIG/HPO-Mapper` | 현재 RARE_DX_AI 서비스 |
|---|---|---|---|
| 핵심 목적 | HPO ontology graph의 각 HPO node를 vector로 학습 | clinical finding text를 표준 HPO term으로 매핑 | HPO term 기반 rare disease candidate ranking과 graph evidence 제공 |
| 문제 정의 | `HPO term`과 `HPO term` 사이의 유사도 학습 | `free text / finding`과 `HPO term` 사이의 매핑 | `patient HPO set`과 `disease profile` 사이의 ranking |
| 입력 | HPO DAG, HPO term frequency table | finding, anatomical region, HPO synonym embedding DB | HPO ID list 또는 clinical note |
| 출력 | HPO node embedding vector | HPO ID, HPO term, matched synonym, score, associated genes | disease candidate list, score components, matched/missing phenotypes, genes, graph paths |
| 알고리즘 계열 | Graph representation learning | Semantic retrieval / phenotype normalization | Hybrid retrieval and re-ranking |
| 주요 모델 | Node2Vec / Node2Vec+ | Embedding cosine similarity + optional LLM | IC overlap, SapBERT sentence-transformer, FAISS, Neo4j evidence, linear reranking |
| 그래프 사용 여부 | 강하게 사용한다. HPO `IS_A` DAG 위에서 random walk 수행 | 직접 graph walk를 하지는 않는다. HPO term/synonym embedding DB를 검색 | Neo4j Disease-Gene-Phenotype graph를 evidence와 graph score 계산에 사용 |
| HPO ontology 구조 사용 | HPO DAG의 parent-child 구조를 학습에 직접 사용 | HPO term/synonym/definition 중심. ontology 구조 학습은 핵심이 아님 | 현재 IC baseline은 direct phenotype overlap 중심. `IS_A` ancestor-aware similarity는 아직 미구현 |
| edge weight 의미 | HPO DAG random walk 확률을 조정하는 값 | edge weight 개념은 핵심이 아니다 | Neo4j relationship에는 `frequency`, `evidence`, `source`를 저장하지만 현재 ranking weight로 직접 쓰지는 않음 |
| edge weight 계산 | `default_weight + min(parent.prob_descendants, child.prob_descendants)` | 해당 없음 | graph score는 `matched phenotype count / query phenotype count`; hybrid score는 `0.45*IC + 0.35*embedding + 0.20*graph` |
| frequency 사용 | clinical note corpus에서 phenotype frequency를 계산해 HPO node probability로 반영 | 기본 알고리즘은 text embedding similarity 중심 | HPOA frequency는 Neo4j edge property로 저장. 현재 score 계산에는 제한적으로만 사용 |
| embedding 생성 방식 | HPO graph random walk -> skip-gram 학습 -> HPO node vector 생성 | query text와 HPO synonym term을 embedding model로 vector화 | HPO term의 `name + definition`을 SapBERT로 embedding하고 disease vector는 associated HPO vectors 평균 |
| similarity 계산 | 학습된 HPO node embedding 간 cosine similarity | query embedding과 HPO synonym embedding 간 cosine similarity | normalized vector inner product를 FAISS에서 검색해 cosine similarity처럼 사용 |
| LLM 사용 | 없음 | Protocol 2/3에서 선택적으로 사용 | 없음. LLM explanation과 LLM HPO mapper는 아직 미구현 |
| Protocol 구분 | weight system: `equal`, `random`, `probabilistic`, `probabilistic_with_bias`; Node2Vec/Node2Vec+ | P1: embedding only, P2: embedding + LLM QC, P3: embedding top-k + LLM selection | `/api/retrieval/ic`, `/api/retrieval/embedding`, `/api/retrieval/hybrid`, `/api/graph/evidence`, note retrieval |
| 학습 필요 여부 | 필요하다. Node2Vec skip-gram 학습을 수행한다 | 보통 사전계산된 embedding DB를 사용하고, 입력 query embedding만 계산한다 | 별도 학습 없음. processed HPO data, FAISS index, Neo4j graph를 build/load |
| clinical note 직접 처리 | 직접 처리하지 않는다. note corpus는 frequency table 생성에 사용된다 | 직접 처리한다. finding + region을 HPO로 변환한다 | dictionary matcher로 직접 처리한다. HPO name/synonym phrase가 note에 등장해야 잘 잡힌다 |
| note-to-HPO 방식 | 해당 없음 | embedding similarity 기반 semantic mapping | exact/phrase dictionary matching |
| gene 연결 | 주요 목적은 아니다 | HPO term에 associated genes를 붙여 출력한다 | disease-gene, gene-phenotype 관계를 Neo4j에 저장하고 candidate response에 associated genes 제공 |
| RARE_DX_AI에서의 위치 | Baseline 3: HPO graph embedding + FAISS 후보 | Baseline 4: clinical note-to-HPO mapper 후보 | 현재 v1 baseline implementation |
| disease ranking에 쓰는 방법 | HPO vector를 평균내 patient/disease vector를 만들고 FAISS 검색 가능 | note를 HPO term으로 바꾼 뒤, 기존 IC/SapBERT/Neo4j ranking pipeline에 입력 | IC score, SapBERT/FAISS embedding score, graph coverage score를 선형 조합 |
| 장점 | ontology 구조와 phenotype frequency를 embedding에 반영 | 실제 임상 표현을 HPO로 바꾸는 앞단 문제에 직접 대응 | 해석 가능하고 재현 가능하다. 각 후보에 score component와 graph evidence를 제공 |
| 한계 | free text를 HPO로 바로 바꾸지는 못한다 | HPO graph 구조나 IC semantic similarity를 직접 학습하지는 않는다 | direct overlap과 dictionary matching에 의존한다. graph embedding, LLM mapper, ancestor-aware IC는 아직 없음 |

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

두 저장소와 현재 서비스 구현을 함께 놓으면 역할이 다르다.

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

### 현재 RARE_DX_AI 적용 위치

```text
HPO terms 또는 dictionary-extracted HPO terms
-> IC direct overlap
-> SapBERT disease embedding + FAISS
-> Neo4j Disease-Gene-Phenotype graph evidence
-> linear hybrid re-ranking
```

현재 서비스는 graph embedding이나 LLM mapper를 아직 사용하지 않는다. 대신 해석 가능한 baseline을 먼저 완성하기 위해 IC score, biomedical text embedding retrieval, graph coverage evidence를 조합한다.

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

## HPO-Mapper와 현재 RARE_DX_AI 서비스의 아키텍처 관계

`UoS-HGIG/HPO-Mapper`는 현재 RARE_DX_AI의 `SapBERT disease embedding + FAISS`를 그대로 대체하는 모듈이 아니다. 아키텍처 상에서는 그보다 앞단의 clinical note-to-HPO 변환 모듈에 가깝다.

현재 RARE_DX_AI 흐름은 다음과 같다.

```text
clinical note
-> dictionary matcher
-> HPO terms
-> IC overlap
-> SapBERT disease embedding + FAISS
-> Neo4j graph evidence
-> hybrid re-ranking
-> disease candidates
```

여기서 `SapBERT sentence-transformer`는 다음 역할을 한다.

```text
HPO terms
-> HPO term name + definition embedding
-> disease embedding과 cosine similarity
-> disease candidate retrieval
```

반면 `HPO-Mapper`는 다음 역할을 한다.

```text
clinical note / finding text
-> HPO synonym embedding search
-> HPO terms
```

즉 위치가 다르다.

```text
현재 dictionary matcher 자리:
clinical note -> HPO terms

SapBERT/FAISS 자리:
HPO terms -> disease candidates
```

따라서 `HPO-Mapper`는 `SapBERT/FAISS disease retrieval`을 갈아끼우는 모듈이 아니라, 현재의 dictionary matcher를 대체하거나 보완하는 모듈이다.

| 모듈 | 현재 RARE_DX_AI 역할 | HPO-Mapper와 관계 |
|---|---|---|
| Dictionary matcher | clinical note에서 HPO term 추출 | HPO-Mapper가 대체 가능 |
| IC overlap | HPO term과 disease phenotype 직접 overlap ranking | HPO-Mapper가 대체하지 않음 |
| SapBERT + FAISS | HPO profile embedding으로 disease retrieval | HPO-Mapper가 직접 대체하지 않음 |
| Neo4j graph evidence | disease-gene-phenotype 근거 조회 | HPO-Mapper가 대체하지 않음 |
| Hybrid reranking | IC/embedding/graph score 조합 | HPO-Mapper가 대체하지 않음 |

가장 자연스러운 통합 방식은 다음과 같다.

```text
clinical note
-> HPO-Mapper
-> mapped HPO terms
-> IC overlap
-> SapBERT disease embedding + FAISS
-> Neo4j graph evidence
-> hybrid re-ranking
```

다만 `HPO-Mapper`의 embedding 방식을 응용해 HPO term retrieval module을 만들 수는 있다. 하지만 이것도 disease retrieval이 아니라 여전히 `text -> HPO` 문제다.

`SapBERT disease embedding + FAISS`를 대체하려면 대체 모듈은 다음 형태여야 한다.

```text
patient HPO set 또는 patient HPO embedding
-> disease embedding index
-> disease candidates
```

예를 들면 `phenotype_embedding / Node2Vec HPO graph embedding + FAISS`가 SapBERT disease embedding과 더 동등한 비교군이다.

정리:

```text
HPO-Mapper는 SapBERT/FAISS의 대체재가 아니다.
HPO-Mapper는 dictionary matcher의 대체재 또는 고도화 버전이다.
SapBERT/FAISS의 대체재 후보는 phenotype_embedding 같은 HPO graph embedding 방식이다.
```

아키텍처 상의 권장 분리는 다음과 같다.

```text
Input Layer:
- dictionary matcher
- HPO-Mapper
- future LLM/NER mapper

Retrieval Layer:
- IC overlap
- SapBERT + FAISS
- future HPO graph embedding + FAISS

Graph Layer:
- Neo4j evidence

Reranking Layer:
- hybrid score
```

## 결론

`phenotype_embedding`, `HPO-Mapper`, 현재 RARE_DX_AI 서비스는 모두 HPO 기반 embedding 또는 retrieval을 다루지만 목적이 다르다.

- `phenotype_embedding`: HPO graph 구조를 학습해 HPO term vector를 만든다.
- `HPO-Mapper`: clinical text를 HPO term으로 변환한다.
- 현재 RARE_DX_AI: HPO term set을 이용해 disease candidate를 ranking하고 Neo4j graph evidence를 제공한다.

따라서 RARE_DX_AI에서는 세 방식을 같은 평가축에 억지로 묶기보다, 다음처럼 분리해서 실험하는 것이 적절하다.

- 현재 구현: v1 interpretable ranking baseline
- `phenotype_embedding`: HPO graph embedding retrieval baseline
- `HPO-Mapper`: clinical note-to-HPO mapping baseline
