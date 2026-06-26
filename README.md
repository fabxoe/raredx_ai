# RARE_DX_AI

RARE_DX_AI는 HPO phenotype 정보를 기반으로 rare disease candidate를 우선순위화하고, Neo4j graph evidence를 함께 제공하는 연구용 prototype이다.

이 시스템은 진단 도구가 아니라 candidate prioritization과 설명 가능한 retrieval 실험을 위한 프로젝트다.

## 현재 구현 범위

- HPO 원천 데이터 로더
- Disease-Gene-Phenotype ETL
- Neo4j knowledge graph
- IC 기반 baseline ranking
- SapBERT 기반 disease embedding
- FAISS disease index
- Hybrid re-ranking
- Dictionary 기반 clinical note to HPO matcher
- 선택형 Doc2HPO/HPO-Mapper adapter
- FastAPI retrieval API
- 고객용 disease ranking 및 knowledge graph 프론트엔드
- Neo4j Browser 기반 graph 시각화

아직 구현하지 않은 것:

- Biomedical NER 기반 HPO mapper
- 내장 LLM 기반 HPO mapper
- LLM explanation generation
- GNN 실험

## 프로젝트 구조

```text
app/        # FastAPI, retrieval, embedding, graph, ETL 구현
scripts/    # HPO 다운로드, processed build, FAISS build, Neo4j load
tests/      # loader, baseline, API 테스트
docs/       # Neo4j 시각화, Cloudflare Tunnel 호스팅 문서
data/       # raw/processed 데이터 위치. 실제 데이터는 Git에 올리지 않음
src/        # 향후 NLP, graph, model 실험용 skeleton
notebooks/  # 향후 EDA/실험 notebook
reports/    # 향후 보고서/그림
```

## 요구사항

- Python 3.12
- uv
- Docker Desktop
- Git

macOS에서 uv가 없으면:

```bash
brew install uv
```

Homebrew를 쓰고 싶지 않다면 uv 공식 설치 스크립트를 사용한다.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

설치 후 새 터미널을 열거나 shell 설정을 다시 로드한 뒤 확인한다.

```bash
uv --version
```

Docker Desktop이 없으면:

```bash
brew install --cask docker
open -a Docker
```

설치 확인:

```bash
uv --version
docker --version
docker info
```

`docker info`에서 Docker daemon 연결 오류가 나면 Docker Desktop이 아직 실행되지 않은 것이다.

```bash
open -a Docker
```

macOS에 `python` 명령이 없을 수 있다. 이 프로젝트 스크립트는 팀원 환경 차이를 줄이기 위해 아래처럼 `uv run scripts/...` 형식으로 실행하는 것을 권장한다.

```bash
uv run scripts/download_hpo.py
uv run pytest ...
```

## 로컬 실행 순서

1. 저장소 clone

```bash
git clone https://github.com/fabxoe/raredx_ai.git
cd raredx_ai
```

2. 환경변수 파일 생성

```bash
cp .env.example .env
```

3. Python dependency 설치

```bash
uv sync
```

4. Neo4j 실행

```bash
docker compose up -d neo4j
```

Neo4j 상태 확인:

```bash
docker compose ps
```

5. 공식 HPO 데이터 다운로드

```bash
uv run scripts/download_hpo.py
```

6. processed knowledge base 생성

```bash
uv run scripts/build_processed.py
```

예상 출력:

```text
Processed knowledge base written: ... phenotypes, ... disease-phenotype annotations, ... gene-phenotype annotations
```

7. FAISS disease index 생성

```bash
uv run scripts/build_faiss.py
```

첫 실행 시 SapBERT model 다운로드와 embedding 계산 때문에 시간이 걸릴 수 있다.

8. Neo4j graph 적재

```bash
uv run scripts/load_neo4j.py
```

9. FastAPI 실행

```bash
uv run uvicorn app.main:app --reload --port 8010
```

API 문서:

```text
http://127.0.0.1:8010/docs
```

고객용 프론트엔드:

```text
http://127.0.0.1:8010/
```

Cloudflare 배포 환경:

```text
https://api.cromtind.uk/
```

프론트엔드는 HPO/clinical note 입력, IC·embedding·hybrid ranking, candidate evidence, Disease-Gene-Phenotype graph를 제공한다. Neo4j Bolt와 계정 정보는 FastAPI 내부에서만 사용하며 고객에게 노출하지 않는다.

Neo4j Browser:

```text
http://localhost:7474
```

Neo4j 로그인:

```text
Username: neo4j
Password: raredx_password
Database: neo4j
```

## 샘플 요청

### IC baseline

```bash
curl -X POST http://127.0.0.1:8010/api/retrieval/ic \
  -H "Content-Type: application/json" \
  -d '{"hpo_terms":["HP:0001250","HP:0001263","HP:0000252"],"top_k":5}'
```

### Embedding retrieval

```bash
curl -X POST http://127.0.0.1:8010/api/retrieval/embedding \
  -H "Content-Type: application/json" \
  -d '{"hpo_terms":["HP:0001250","HP:0001263","HP:0000252"],"top_k":5}'
```

### Hybrid retrieval

```bash
curl -X POST http://127.0.0.1:8010/api/retrieval/hybrid \
  -H "Content-Type: application/json" \
  -d '{"hpo_terms":["HP:0001250","HP:0001263","HP:0000252"],"top_k":5}'
```

### Clinical note 입력

Clinical note 입력은 `hpo_mapper`로 앞단 HPO mapper를 선택할 수 있다.

지원 모드:

- `dictionary`: 기본값. HPO name/synonym phrase를 note에서 직접 찾는다.
- `doc2hpo`: 외부 Doc2HPO/HPO-Mapper 호환 endpoint를 호출한다.
- `dictionary_doc2hpo`: dictionary와 Doc2HPO 결과를 병합한다.
- `off`: note mapper를 끈다. 이 경우 note endpoint는 400을 반환하고 HPO 직접 입력을 사용해야 한다.

`doc2hpo` 모드는 `.env`에 외부 endpoint를 설정해야 한다.

```text
RAREDX_DOC2HPO_URL=http://127.0.0.1:9000/map
RAREDX_DOC2HPO_TIMEOUT_SECONDS=20
```

외부 endpoint는 `POST` JSON 요청을 받아 HPO 후보 목록을 JSON으로 반환해야 한다. 지원하는 응답 key는 `extracted_phenotypes`, `hpo_terms`, `matches`, `results`, `mapped_terms` 중 하나다.

```bash
curl -X POST http://127.0.0.1:8010/api/retrieval/note/ic \
  -H "Content-Type: application/json" \
  -d '{"clinical_note":"The patient has seizure, global developmental delay, and microcephaly.","top_k":3,"hpo_mapper":"dictionary"}'
```

### Graph evidence

```bash
curl -X POST http://127.0.0.1:8010/api/graph/evidence \
  -H "Content-Type: application/json" \
  -d '{"hpo_terms":["HP:0001250","HP:0001263"],"top_k":5}'
```

### Graph subgraph

```bash
curl -X POST http://127.0.0.1:8010/api/graph/subgraph \
  -H "Content-Type: application/json" \
  -d '{"hpo_terms":["HP:0001250","HP:0001263"],"top_k":5}'
```

## Neo4j 시각화

Neo4j Browser에서 Cypher query로 graph를 확인할 수 있다.

자세한 예제:

- [Neo4j 시각화 예제](docs/neo4j_visualization_examples.md)

## 팀 공유 호스팅

남는 맥북에서 FastAPI와 Neo4j Browser를 실행하고 Cloudflare Tunnel로 팀원에게 공유할 수 있다.

호스팅 문서:

- [Cloudflare Tunnel 기반 팀 공유 호스팅](docs/cloudflare_tunnel_hosting.md)

## 개발 히스토리

현재까지의 구현 이력과 다음 계획:

- [개발 히스토리](DEVELOPMENT_HISTORY.md)

## 테스트

```bash
uv run pytest -q
```

현재 기준:

```text
9 passed
```

## Git에 올리지 않는 데이터

아래 파일은 각자 로컬에서 생성한다.

```text
data/raw/*
data/processed/*
data/processed/faiss/*
Neo4j Docker volume
model cache
.env
```

즉 GitHub에는 코드, 스크립트, 설정, 문서, 테스트 fixture만 올린다.

## 설치 상태 점검

다른 노트북에서 setup이 막히면 먼저 아래 명령으로 누락된 항목을 확인한다.

```bash
uv run scripts/check_setup.py
```

자주 발생하는 문제:

```text
zsh: command not found: docker
```

Docker Desktop이 설치되지 않았거나 PATH에 없는 상태다.

```bash
brew install --cask docker
open -a Docker
```

```text
Cannot connect to the Docker daemon
```

Docker Desktop이 실행 중이 아니다.

```bash
open -a Docker
```

```text
zsh: command not found: python
```

macOS에서 `python` alias가 없는 상태다. 이 프로젝트 스크립트는 `uv run scripts/...` 형식으로 실행한다.

```bash
uv run scripts/download_hpo.py
```

```text
FileNotFoundError: data/processed/phenotypes.json
```

processed 데이터가 아직 생성되지 않은 상태다. 아래 순서를 먼저 실행한다.

```bash
uv run scripts/download_hpo.py
uv run scripts/build_processed.py
uv run scripts/build_faiss.py
```

```text
zsh: command not found: uvicorn
```

가상환경 밖에서 `uvicorn`을 직접 실행한 것이다.

```bash
uv run uvicorn app.main:app --reload --port 8010
```

## Codex로 이어서 작업할 때

다른 맥북에서 VSCode/Codex를 열고 다음처럼 요청한다.

```text
Read AGENTS.md
Read PROJECT_CONTEXT.md
Read DEVELOPMENT_HISTORY.md
Then continue setting up or developing RARE_DX_AI.
```
