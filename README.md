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
- FastAPI retrieval API
- Neo4j Browser 기반 graph 시각화

아직 구현하지 않은 것:

- Biomedical NER 기반 HPO mapper
- LLM 기반 HPO mapper
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

Docker Desktop이 없으면:

```bash
brew install --cask docker
open -a Docker
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
python scripts/download_hpo.py
```

6. processed knowledge base 생성

```bash
python scripts/build_processed.py
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
python scripts/load_neo4j.py
```

9. FastAPI 실행

```bash
uvicorn app.main:app --reload --port 8010
```

API 문서:

```text
http://127.0.0.1:8010/docs
```

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

현재 note mapper는 dictionary 기반이다. Biomedical NER 또는 LLM mapper는 아직 아니다.

```bash
curl -X POST http://127.0.0.1:8010/api/retrieval/note/ic \
  -H "Content-Type: application/json" \
  -d '{"clinical_note":"The patient has seizure, global developmental delay, and microcephaly.","top_k":3}'
```

### Graph evidence

```bash
curl -X POST http://127.0.0.1:8010/api/graph/evidence \
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
pytest -q
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

## Codex로 이어서 작업할 때

다른 맥북에서 VSCode/Codex를 열고 다음처럼 요청한다.

```text
Read AGENTS.md
Read PROJECT_CONTEXT.md
Read DEVELOPMENT_HISTORY.md
Then continue setting up or developing RARE_DX_AI.
```
