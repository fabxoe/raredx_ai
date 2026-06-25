# RARE_DX_AI 개발 히스토리

## 2026-06-26

### 두 종류의 Doc2HPO/HPO Mapper 계열 비교

Doc2HPO 계열 도구는 현재 disease ranking baseline과 같은 층이 아니라, clinical note를 HPO term으로 변환하는 upstream mapper baseline으로 분리해서 본다.

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

고객 공개 주소:

```text
https://api.cromtind.uk/
```

관리자용 Neo4j Browser는 고객 UI와 분리한다.

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

3. 고객용 Graph Explorer 구현
   - `Customer Workspace`에서 HPO, Disease, Gene를 검색하고 연결 관계를 탐색할 수 있게 한다.
   - 시작 노드, 관계 종류, 탐색 깊이, 결과 개수를 안전한 UI control로 제공한다.
   - 결과를 Graph/Table view로 제공하고 선택한 노드의 evidence를 별도 inspector에 표시한다.
   - 자주 사용하는 탐색 조건은 query preset으로 제공한다.
   - 고객에게 raw Cypher, Bolt 주소, Neo4j 계정 정보를 노출하지 않는다.
   - 서버에서 검증된 query template만 실행해 과도한 graph traversal을 제한한다.

4. 관리자용 Cypher Lab 구현
   - `Admin Workspace`로 분리하고 Cloudflare Access 인증을 통과한 관리자와 연구자만 접근하게 한다.
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
