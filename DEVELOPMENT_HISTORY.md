# RARE_DX_AI 개발 히스토리

## 2026-06-27

### Original HPO-Mapper adapter 실제 연동 경계 구현

원본 `UoS-HGIG/HPO-Mapper`의 P1/P2/P3 프로토콜을 RARE_DX_AI의 clinical note-to-HPO extraction 단계에 붙일 수 있도록 전용 adapter를 추가했다.

- `OriginalHPOMapperAdapter`를 추가했다.
  - `protocol`, `top_k`, `threshold/min_sim`, `embed_model`, `llm.enabled/provider/chat_model`을 wrapper endpoint로 전달한다.
  - 원본 repo의 CSV/JSON 출력에 가까운 `finding`, `region`, `hpo_id`, `hpo_term`, `matched_term`, `genes`, `score/similarity`, `flag` 필드를 내부 `ExtractedPhenotype`으로 변환한다.
  - `HP_0001250`, `http://purl.obolibrary.org/obo/HP_0001250` 같은 ID 표현을 `HP:0001250`로 정규화한다.
- `RetrievalService.original_hpo_mapper`가 generic Doc2HPO adapter 대신 전용 adapter를 사용하도록 변경했다.
- README에 원본 HPO-Mapper wrapper endpoint의 요청/응답 계약을 추가했다.
- 테스트를 추가했다.
  - P2 스타일 row 파싱
  - P3 스타일 nested result 파싱
  - protocol payload 생성

남은 한계:

- 원본 HPO-Mapper repo 자체를 RARE_DX_AI 프로세스 안에 직접 import하지는 않는다.
- 실제 실행은 별도 wrapper service가 필요하며, `.env`의 `RAREDX_ORIGINAL_HPO_MAPPER_URL`로 연결한다.
- P2/P3의 LLM 동작 품질은 wrapper service와 선택한 LLM provider/model 설정에 의존한다.

### Original HPO-Mapper FastAPI wrapper 구현

원본 HPO-Mapper의 실행 방식을 RARE_DX_AI에서 호출 가능한 HTTP service로 감싸는 wrapper를 추가했다.

- `app/original_hpo_mapper_wrapper.py`를 추가했다.
  - `POST /map`: clinical note 또는 structured finding list를 HPO term 후보로 매핑한다.
  - `GET /health`: SQLite embedding DB, gene map, HPO definition 로드 상태를 확인한다.
- 원본 HPO-Mapper와 같은 핵심 입력 artifact를 사용한다.
  - `hpo_synonym_embeddings(hpo_id, hpo_name, term, embedding)` SQLite table
  - `hpo_gene(hpo_id, genes)` SQLite table
  - 선택 사항: HPO JSON definition file
- embedding 생성은 Ollama HTTP API의 `nomic-embed-text`를 사용한다.
- P1/P2/P3 프로토콜을 wrapper 요청 단위로 받는다.
  - P1: embedding similarity 기반 best match
  - P2: LLM QC flag
  - P3: LLM selection
- OpenAI/Ollama LLM QC는 기존 `PhenotypeLLMSelector`를 재사용한다.
- `.env.example`과 README에 wrapper 실행 환경변수를 추가했다.
- 테스트를 추가했다.
  - 작은 SQLite fixture 기반 P1 mapping
  - `/health` 상태 확인

실행 예:

```bash
uv run uvicorn app.original_hpo_mapper_wrapper:app --reload --port 9001
```

### Original HPO-Mapper 실데이터 기동 검증

Hugging Face Space `UoS-HGIG/HPOmapper`에서 원본 wrapper 실행에 필요한 asset을 내려받아 로컬에서 기동 검증했다.

- 다운로드 위치:
  - `data/external/original_hpo_mapper/hp.json`
  - `data/external/original_hpo_mapper/hpo_genes_with_synonyms.db`
- 로드 결과:
  - HPO synonym embedding row: 29,723
  - HPO gene row: 11,536
  - HPO definition: 19,651
- Ollama embedding model:
  - `nomic-embed-text`
- 확인한 endpoint:
  - `GET http://127.0.0.1:9001/health`
  - `POST http://127.0.0.1:9001/map`
  - `POST http://127.0.0.1:8010/api/retrieval/note/ic`
- 샘플 clinical note:
  - `The patient has seizure, global developmental delay, and microcephaly.`
- Original HPO-Mapper wrapper 추출 결과:
  - `HP:0001250` Seizure
  - `HP:0001263` Global developmental delay
  - `HP:0000252` Microcephaly
- RARE_DX_AI end-to-end 확인:
  - `hpo_mapper=original_hpo_mapper`
  - query HPO terms가 위 세 항목으로 정상 전달됨
  - IC ranking 후보가 정상 반환됨

추가 조치:

- broad HPO term의 gene list가 너무 커지는 문제를 확인했다.
- wrapper 응답은 기본적으로 gene list를 50개로 제한하고 `gene_count`로 전체 개수를 보존하도록 변경했다.
- 제한값은 `RAREDX_ORIGINAL_HPO_MAPPER_MAX_GENES`로 조정한다.
- HPO 매핑 자체는 gene list 개수 제한의 영향을 받지 않는다.
  - 매핑은 clinical text embedding과 HPO synonym embedding의 cosine similarity로 결정된다.
  - gene list는 매핑 이후 HPO term에 붙는 evidence payload다.
- 프론트 HPO extraction 설정에 `Gene preview` 버튼을 추가했다.
  - 50
  - 100
  - 1000
  - All

보류된 UI 개선 계획:

- `Gene preview`는 ranking 후보 개수(`Candidates Top 5/10/20`)와 역할이 다르지만, 둘 다 "표시 개수"처럼 보여 혼동될 수 있다.
- 이 설정은 `Disease ranking` 블럭으로 옮기지 않고 `HPO extraction` 블럭 안에 유지한다.
  - 이유: gene preview는 Original HPO-Mapper가 HPO term에 붙여 반환하는 gene evidence 표시량이므로, disease candidate ranking 수와 섞으면 파이프라인 이해를 방해한다.
- 추후 UI 개선 시 다음 방향을 검토한다.
  - `Gene preview` 명칭을 `HPO-gene evidence` 또는 `Gene evidence detail`로 변경한다.
  - 기본값은 50으로 두고, `50 / 100 / 1000 / All`은 접힘/확장형 고급 옵션으로 둔다.
  - 툴팁 또는 짧은 설명으로 "ranking 후보 개수에는 영향을 주지 않고, mapped HPO term별 gene evidence 표시량만 바꾼다"를 명시한다.
  - `Candidates` 옵션에 `All`을 추가해서 gene preview와 연결하는 방식은 우선 채택하지 않는다.

## 2026-06-26

### 선택형 HPO mapper mode 구현

Clinical note 입력 앞단의 HPO mapper를 켜고 끌 수 있게 구현했다.

- `ClinicalNoteRetrievalRequest`에 `hpo_mapper`를 추가했다.
- 지원 모드:
  - `dictionary`
  - `doc2hpo`
  - `dictionary_doc2hpo`
- 기본값은 기존 동작과 같은 `dictionary`다.
- `doc2hpo` 모드는 외부 Doc2HPO/HPO-Mapper 호환 endpoint를 호출하는 adapter로 구현했다.
- 외부 endpoint는 `RAREDX_DOC2HPO_URL`로 설정한다.
- 설정이 없는데 `doc2hpo`를 선택하면 503으로 명확히 실패한다.
- API 호환성을 위해 `off` mode 처리는 남겨두지만, 프론트엔드 HPO extraction 선택지에서는 제외했다.
  - Clinical note 입력은 `dictionary`를 기본값으로 사용한다.
  - HPO를 직접 입력하려면 `HPO terms` 탭을 사용한다.
- 고객용 프론트엔드 Clinical note 입력 영역에 mapper 선택 control을 추가했다.
- 테스트를 추가했다.
  - dictionary 기본 응답에 mapper mode 포함
  - mapper off 상태 처리
  - Doc2HPO 미설정 상태 처리

Mapper 비교와 확장 가능한 설정 구조를 추가했다.

- `/api/hpo-mappers`에서 사용 가능한 mapper와 설정 option을 반환한다.
- `/api/hpo-mappers/compare`에서 여러 mapper 결과를 같은 clinical note 기준으로 비교할 수 있는 backend 구조를 추가했다.
- Original HPO-Mapper adapter를 위한 endpoint 설정을 분리했다.
  - `RAREDX_ORIGINAL_HPO_MAPPER_URL`
- Original HPO-Mapper의 protocol, LLM on/off, top-k, threshold, model 설정을 프론트에서 렌더링할 수 있게 capability schema를 추가했다.
- 프론트는 mapper 버튼과 설정 form을 backend capability 기반으로 동적으로 렌더링한다.
- HPO mapper 결과 schema에 `metadata`를 추가했다.
  - source, candidate rank, threshold, embedding model, LLM provider/model/protocol, QC status를 기록할 수 있다.
- LLM QC/selection 레이어를 추가했다.
  - OpenAI Chat Completions JSON 응답을 우선 지원한다.
  - Ollama `/api/chat` JSON 응답을 로컬 fallback으로 지원한다.
  - LLM은 새 HPO를 만들지 않고 mapper 후보 중 선택/제외만 수행한다.

Disease ranking option 구조를 추가했다.

- HPO extraction 옵션과 Disease ranking 옵션을 분리했다.
  - HPO extraction 옵션: Doc2HPO threshold, candidate limit, LLM QC/selection 등
  - Disease ranking 옵션: disease embedding backend, hybrid weight, graph evidence mode 등
- `/api/retrieval/ranking-methods`에서 ranking method capability를 반환한다.
- `RetrievalRequest`와 `ClinicalNoteRetrievalRequest`에 `ranking_options`를 추가했다.
- Clinical note 입력에서도 `Embedding` ranking을 직접 호출할 수 있게 `POST /api/retrieval/note/embedding`을 추가했다.
- 현재 지원하는 disease embedding backend는 `sapbert_faiss` 하나로 제한했다.
- `Hybrid` 선택 시 요청별로 `ic_weight`, `embedding_weight`, `graph_weight`를 바꿀 수 있게 했다.
- 프론트엔드는 `HPO extraction`과 `Disease ranking` 섹션을 나누고, backend capability 기반으로 option form을 렌더링한다.

### 두 종류의 Doc2HPO/HPO Mapper 계열 비교

Doc2HPO 계열 도구는 현재 disease ranking baseline과 같은 층이 아니라, clinical note를 HPO term으로 변환하는 upstream mapper baseline으로 분리해서 본다.

팀 공유용 비교 문서를 추가했다.

- `docs/doc2hpo_repository_comparison.md`

현재 RARE_DX_AI 서비스에 적용된 알고리즘을 같은 비교표에 추가했다.

- IC direct overlap
- SapBERT disease embedding + FAISS
- Neo4j graph evidence
- dictionary-based clinical note matcher
- linear hybrid re-ranking

HPO-Mapper와 현재 RARE_DX_AI 서비스의 아키텍처 관계를 문서에 추가했다.

- HPO-Mapper는 `SapBERT disease embedding + FAISS`의 대체재가 아니다.
- HPO-Mapper는 dictionary matcher를 대체하거나 보완하는 `clinical note -> HPO terms` 모듈이다.
- SapBERT/FAISS의 동등한 대체 후보는 `phenotype_embedding` 같은 HPO graph embedding + FAISS 방식이다.

비교 대상:

1. `phenotype_embedding`
   - HPO ontology DAG 위에서 Node2Vec 또는 Node2Vec+ 기반 graph embedding을 학습한다.
   - clinical note에서 얻은 phenotype frequency를 HPO node의 propagated probability로 반영한다.
   - edge weight는 HPO `IS_A` graph에서 random walk 확률을 조정하기 위한 값이다.
   - 우리 프로젝트에서는 `SapBERT disease embedding + FAISS`와 별도의 `HPO graph embedding + FAISS` baseline 후보로 본다.

2. `UoS-HGIG/HPO-Mapper`
   - clinical finding text를 HPO term 후보로 매핑하는 도구다.
   - embedding similarity 기반 HPO retrieval을 사용하고, 설정에 따라 LLM quality control 또는 term selection을 붙일 수 있다.
   - 우리 프로젝트에서는 dictionary matcher의 다음 비교군인 `clinical note-to-HPO mapping baseline`으로 본다.

정리:

- Baseline 1: IC-weighted HPO overlap
- Baseline 2: SapBERT disease embedding + FAISS
- Baseline 3: HPO graph embedding 또는 Node2Vec phenotype embedding + FAISS
- Baseline 4: Clinical note-to-HPO mapper
  - Dictionary matcher
  - HPO Mapper/Doc2HPO-style embedding mapper
  - LLM-assisted HPO mapper

평가 기준은 분리한다.

- Baseline 1~3은 gold HPO term이 주어졌을 때 disease candidate ranking을 평가한다.
- Baseline 4는 clinical note에서 HPO term을 얼마나 잘 추출하고 정규화하는지 평가한다.
- Baseline 4의 출력 HPO를 ranking pipeline에 넣어 end-to-end 성능도 별도로 확인한다.

현재 판단:

HPO Mapper/Doc2HPO 계열은 v1 ranking baseline을 대체하지 않는다. 대신 dictionary matcher의 한계를 보완하는 HPO normalization/mapping 단계로 추가하는 것이 적절하다. 이후 `clinical note -> HPO terms -> disease ranking -> graph evidence` 흐름에서 mapper별 성능 차이를 비교한다.

## 2026-06-24

### 고객용 프론트엔드 추가

- FastAPI root(`/`)에서 고객용 작업 화면을 제공하도록 구현했다.
- HPO term 검색과 선택 기능을 추가했다.
- Clinical note 기반 HPO 추출 및 ranking 입력을 연결했다.
- IC, SapBERT+FAISS embedding, hybrid ranking 선택 기능을 추가했다.
- Candidate disease ranking table과 score component 비교를 추가했다.
- Neo4j를 FastAPI 뒤에 숨기고 고객에게 node/edge JSON만 반환하는 subgraph API를 추가했다.
  - `POST /api/graph/subgraph`
- Cytoscape.js 기반 Disease-Gene-Phenotype graph 시각화를 추가했다.
- Disease row/node 선택 시 evidence와 연결 node를 강조하도록 구현했다.
- Neo4j 연결 실패 시에도 disease ranking 결과는 유지하도록 처리했다.
- 데스크톱 1440x900과 모바일 500px viewport에서 렌더링을 확인했다.
- 전체 테스트 결과: `11 passed`

현재 팀 공유 주소:

```text
https://api.cromtind.uk/
```

현재 접근 권한 모델:

- 나를 포함한 팀원 7명은 모두 관리자/연구자 권한으로 둔다.
- 현재 FastAPI 화면은 팀 내부 연구/시연용 workspace로 사용한다.
- 향후 외부 사용자 또는 잠정 고객에게 제공할 화면은 `Graph Explorer`로 별도 제품 UX를 완성한다.
- `Cypher Lab`은 팀원 7명이 Neo4j graph를 점검하는 관리자 도구로 둔다.
- Neo4j Browser는 개발 및 장애 대응용 보조 도구로 유지하고, 장기적으로는 `Cypher Lab`으로 대체한다.

## 2026-06-22

### 현재 개발 초점

GNN 실험을 바로 시작하기 전에 v1 연구용 baseline을 먼저 완성한다.

우선순위:

1. HPO 원천 데이터 로더 구축
2. Neo4j 스키마 설계
3. Disease-Gene-Phenotype ETL 파이프라인
4. FAISS 인덱스 생성
5. Retrieval API
6. Graph Retrieval API
7. IC 기반 Baseline
8. Embedding Baseline
9. Re-ranking
10. GNN 실험

현재 연구 판단:

GNN은 의도적으로 뒤로 미룬다. 먼저 IC scoring, embedding retrieval, Neo4j graph evidence 기반의 해석 가능한 비교군을 안정적으로 만든 뒤, 그 결과를 기준으로 GNN 성능 향상 실험을 진행하는 것이 더 적절하다.

### 완료된 작업

- `app/` 기반 FastAPI 애플리케이션 구조를 추가했다.
- Docker Compose 기반 Neo4j 개발 환경을 추가했다.
- HPO 원천 데이터 다운로드 스크립트를 추가했다.
- HPO OBO 파서를 추가했다.
- `phenotype.hpoa` disease-phenotype 로더를 추가했다.
- `genes_to_phenotype.txt` gene-phenotype 로더를 추가했다.
- local retrieval을 위한 processed JSON 저장 구조를 추가했다.
- Neo4j에 `Disease`, `Phenotype`, `Gene` unique constraint를 추가했다.
- Neo4j ETL을 추가했다.
  - `Disease`
  - `Phenotype`
  - `Gene`
  - `Disease - HAS_PHENOTYPE -> Phenotype`
  - `Disease - ASSOCIATED_WITH -> Gene`
  - `Gene - ASSOCIATED_PHENOTYPE -> Phenotype`
- 전체 HPO 기반 knowledge graph를 로컬 Neo4j에 적재했다.
  - Disease node: 13028개
  - Phenotype node: 19855개
  - Gene node: 5273개
  - Relationship: 592771개
- IC 기반 baseline ranking을 추가했다.
- `cambridgeltl/SapBERT-from-PubMedBERT-fulltext` 기반 biomedical embedding baseline을 추가했다.
- FAISS disease embedding index 생성 기능을 추가했다.
- 로컬 FAISS index를 생성했다.
- Retrieval endpoint를 추가했다.
  - `POST /api/retrieval/ic`
  - `POST /api/retrieval/embedding`
  - `POST /api/retrieval/hybrid`
- Graph evidence endpoint를 추가했다.
  - `POST /api/graph/evidence`
- Dictionary 기반 clinical note HPO matcher를 추가했다.
- Note 기반 retrieval endpoint를 추가했다.
  - `POST /api/retrieval/note/ic`
  - `POST /api/retrieval/note/hybrid`
- 팀 공유용 Neo4j 시각화 예제 문서를 추가했다.
  - `docs/neo4j_visualization_examples.md`
- 남는 맥북과 Cloudflare Tunnel을 이용해 FastAPI와 Neo4j Browser를 팀원에게 공유하는 호스팅 문서를 추가했다.
  - `docs/cloudflare_tunnel_hosting.md`
- 팀원이 다른 노트북에서 clone 후 재현할 수 있도록 `README.md`를 추가했다.
- 팀원 setup 오류를 줄이기 위해 README 실행 명령을 `uv run` 기준으로 보강했다.
- Homebrew를 쓰지 않는 팀원을 위해 uv 공식 설치 스크립트 안내를 README에 추가했다.
- 설치 상태 점검 스크립트를 추가했다.
  - `scripts/check_setup.py`
- 테스트를 추가했다.
  - HPO loader
  - disease-phenotype negative annotation filtering
  - gene-phenotype loading
  - IC baseline ranking
  - retrieval API
  - graph schema constraint
  - clinical note HPO matching

### 주요 수정 사항

- 최신 공식 `phenotype.hpoa` 파일의 소문자 헤더를 처리하도록 로더를 수정했다.
  - `database_id`
  - `disease_name`
  - `qualifier`
  - `hpo_id`
  - `reference`
  - `evidence`
  - `frequency`
- 헤더 불일치 때문에 `disease_phenotypes.json`이 빈 리스트로 생성되던 문제를 수정했다.
- FAISS 의존성은 legacy `faiss`가 아니라 `faiss-cpu`가 맞음을 확인했다.
- FAISS build 과정에서 disease마다 HPO term embedding을 반복 계산하지 않도록 수정했다.
  - HPO term embedding을 한 번 계산한다.
  - disease profile embedding은 관련 HPO vector 평균으로 만든다.
- 대용량 raw/processed 데이터와 FAISS artifact가 git에 들어가지 않도록 `.gitignore`를 보강했다.

### 현재 실행 상태

- Neo4j는 Docker Compose로 실행한다.
- API는 현재 `8010` 포트에서 실행 중이다.
- `8000` 포트는 다른 로컬 앱이 사용 중이다.
- API 문서:
  - `http://127.0.0.1:8010/docs`
- `8000` 포트에서 실행 중인 기존 앱:
  - RareArena HPO Mapping Demo

### 검증한 명령어

```bash
uv run pytest -q
# 9 passed
```

```bash
uv run scripts/build_processed.py
# 19810 phenotypes
# 283976 disease-phenotype annotations
# 331738 gene-phenotype annotations
```

```bash
uv run scripts/build_faiss.py
# FAISS index written to data/processed/faiss
```

```bash
uv run scripts/load_neo4j.py
# Neo4j knowledge graph load completed
```

### 샘플 입력

HPO ID 기반 retrieval:

```json
{
  "hpo_terms": ["HP:0001250", "HP:0001263", "HP:0000252"],
  "top_k": 10
}
```

Clinical note 기반 retrieval:

```json
{
  "clinical_note": "The patient has seizure, global developmental delay, and microcephaly.",
  "top_k": 3
}
```

위 clinical note 예시에서 추출된 HPO term:

- `HP:0001250` Seizure
- `HP:0001263` Global developmental delay
- `HP:0000252` Microcephaly

### 팀 공유 문서

- Neo4j Browser 접속 방법과 Cypher 시각화 예제:
  - `docs/neo4j_visualization_examples.md`
- Cloudflare Tunnel 기반 팀 공유 호스팅 방법:
  - `docs/cloudflare_tunnel_hosting.md`
- 로컬 설치와 실행 가이드:
  - `README.md`

### 현재 한계

- 현재 clinical note mapper는 dictionary 기반이다.
- 아직 biomedical NER 기반 HPO mapper가 아니다.
- 아직 LLM 기반 HPO mapper가 아니다.
- HPO term name 또는 synonym이 note 안에 직접 등장할 때 가장 잘 동작한다.
- `"delayed milestones"`, `"shaking episodes"`처럼 의역된 표현은 놓칠 수 있다.
- IC baseline은 현재 direct phenotype overlap만 사용한다.
- HPO ontology의 ancestor similarity는 아직 반영하지 않았다.
- Hybrid re-ranking은 현재 해석 가능한 선형 가중치 조합이다.
- LLM explanation generation은 아직 구현하지 않았다.
- GNN 실험은 의도적으로 아직 구현하지 않았다.

### 다음 개발 계획

1. HPO normalization 개선
   - 전체 `hp.obo`에서 synonym을 반영해 processed 데이터를 다시 생성한다.
   - alias matching과 단순 phrase normalization을 추가한다.
   - `"no seizure"` 같은 부정 표현 처리를 추가한다.

2. IC baseline 개선
   - `IS_A` 관계를 이용한 ancestor-aware matching을 추가한다.
   - direct overlap과 ancestor-expanded overlap을 비교한다.
   - HPO term별 IC 기여도를 score explanation에 포함한다.

3. 사용자용 Graph Explorer 구현
   - 향후 외부 사용자 또는 잠정 고객 인터페이스로 발전시킬 제품 화면이다.
   - `User Workspace`에서 HPO, Disease, Gene를 검색하고 연결 관계를 탐색할 수 있게 한다.
   - 시작 노드, 관계 종류, 탐색 깊이, 결과 개수를 안전한 UI control로 제공한다.
   - 결과를 Graph/Table view로 제공하고 선택한 노드의 evidence를 별도 inspector에 표시한다.
   - 자주 사용하는 탐색 조건은 query preset으로 제공한다.
   - 일반 사용자에게 raw Cypher, Bolt 주소, Neo4j 계정 정보를 노출하지 않는다.
   - 서버에서 검증된 query template만 실행해 과도한 graph traversal을 제한한다.

4. 관리자용 Cypher Lab 구현
   - 나를 포함한 팀원 7명을 관리자/연구자로 두고 `Admin Workspace`로 분리한다.
   - Cloudflare Access에서 관리자 이메일 7명만 접근하게 한다.
   - Cypher editor에 Run/Stop, 실행 시간, query history, query preset을 제공한다.
   - 결과는 Graph/Table/JSON view로 전환할 수 있게 한다.
   - 기본 실행 권한은 read-only로 제한한다.
   - write query는 별도 권한, 경고, 명시적 확인 절차를 거치게 한다.
   - query timeout, 최대 반환 row 수, audit log를 적용한다.
   - Neo4j Browser는 개발 및 장애 대응용 도구로 유지하고 고객 화면과 분리한다.

5. Graph retrieval 개선
   - `disease_id` 기준 disease-specific evidence endpoint를 추가한다.
   - gene path를 포함한 graph path를 출력한다.
     - `Patient -> Phenotype -> Disease -> Gene`
   - graph coverage metric을 추가한다.

6. Embedding retrieval 개선
   - SapBERT 외 다른 biomedical encoder로 교체 가능한 설정을 정리한다.
   - HPO embedding cache artifact를 추가한다.
   - 작은 curated example 기준 Top-k, MRR 평가 스크립트를 추가한다.

7. Re-ranking 개선
   - IC, embedding, graph score scale을 보정한다.
   - request 또는 환경변수에서 weight를 조정할 수 있게 한다.
   - ablation output을 추가한다.
     - IC only
     - embedding only
     - graph only
     - hybrid

8. Biomedical NER 또는 LLM 기반 HPO mapper는 이후 단계에서 추가한다.
   - Retrieval baseline과 분리해서 구현한다.
   - Dictionary matcher와 비교한다.
   - LLM extraction 결과를 ground truth처럼 취급하지 않는다.

9. GNN 실험은 baseline 평가 이후 시작한다.
   - train/evaluation split을 먼저 정의한다.
   - IC/embedding/graph baseline ranking을 비교군으로 사용한다.
   - clinical diagnosis처럼 보이는 표현은 사용하지 않는다.

### 업데이트 규칙

앞으로 구현 변경이 생기면 이 파일에 다음 항목을 기록한다.

- 날짜
- 변경한 내용
- 왜 변경했는지
- 실행한 명령어와 테스트 결과
- 남은 한계 또는 다음 액션

---

## 2026-06-28 업데이트

### Cloudflare Access 진입 흐름 정리

- 로그아웃 버튼을 앱 헤더에 직접 붙였던 실험은 뒤로 가기 시 이전 화면이 복원되어 사용자에게 서비스 오류처럼 보일 수 있어 롤백했다.
- `www.cromtind.uk` 요청에서 Cloudflare Access 인증 헤더가 없으면 `app/static/login.html`을 반환하도록 했다.
- Cloudflare Access 인증 헤더가 있으면 기존 RARE_DX_AI 메인 화면을 바로 반환한다.
- 로컬 개발 환경(`localhost`, `127.0.0.1`)은 인증 헤더 없이도 기존처럼 메인 화면이 열리게 유지했다.
- `api.cromtind.uk`는 기존처럼 `/docs`로 redirect한다.

검증:

- `uv run pytest`
  - 결과: `24 passed`
- FastAPI TestClient로 확인:
  - `www.cromtind.uk` + Access 헤더 없음: 로그인 페이지 반환
  - `www.cromtind.uk` + `cf-access-authenticated-user-email` 헤더 있음: 메인 페이지 반환
  - `127.0.0.1:8010`: 메인 페이지 반환
  - `api.cromtind.uk`: `/docs` redirect

다음 액션:

- Cloudflare Access에서 `www.cromtind.uk` 보호 정책을 팀원 이메일 기준으로 정리한다.
- 이후 `/logout` 중간 페이지를 추가해 로그아웃 후 로그인 페이지로 자연스럽게 이동시키는 흐름을 구현한다.

---

## 2026-06-28 업데이트

### Graph evidence scoring 설계 문서 추가

- 현재 graph score가 `local_overlap` 기반이라 IC baseline과 중복 신호가 크다는 점을 정리했다.
- `Graph only` ranking은 현재 많은 후보가 1.0으로 묶여 구분력이 약하므로, 우선은 `Hybrid` 내부의 graph evidence component로 강화하는 방향을 설계했다.
- 향후 graph evidence mode 후보를 정리했다.
  - `local_overlap`
  - `gene_path`
  - `frequency_weighted_graph`
  - `source_confidence_graph`
  - `ontology_path_graph`
- 상세 설계는 [graph_evidence_scoring_plan.md](docs/graph_evidence_scoring_plan.md)에 기록했다.

다음 액션:

- UI에서는 `IC | Embedding | Hybrid` 중심 구조를 유지하고, graph는 Hybrid 내부 evidence mode로 정리할지 결정한다.
- 우선 구현 후보는 `frequency_weighted_graph`로 둔다.
