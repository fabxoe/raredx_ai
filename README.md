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

GitHub Actions 운영 문서:

```text
docs/github_actions_deployment.md
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
기본 출력 위치는 `data/processed/faiss/sapbert_faiss/`다. 기존 `data/processed/faiss/disease.faiss` 경로도 읽을 수 있게 유지한다.

PubMedBERT 기반 disease embedding index를 만들려면 다음 명령을 사용한다.

```bash
uv run scripts/build_faiss.py --backend pubmedbert_faiss
```

BioSentVec는 sentence-transformer가 아니라 외부 sentence vector model file과 optional `sent2vec` Python package가 필요하다.
`RAREDX_BIOSENTVEC_MODEL_PATH` 또는 `--model`에 모델 파일 경로를 지정한다.

```bash
uv run scripts/build_faiss.py --backend biosentvec_faiss --model /path/to/biosentvec/model
```

다른 sentence-transformer 모델을 비교하려면 별도 backend/model 조합으로 인덱스를 만든다.

```bash
uv run scripts/build_faiss.py --backend custom_sentence_transformer_faiss --model sentence-transformers/all-MiniLM-L6-v2
```

HPO ontology graph embedding + FAISS 비교군은 SapBERT 모델 다운로드 없이 생성할 수 있다.

```bash
uv run scripts/build_faiss.py --backend hpo_deepwalk_faiss
uv run scripts/build_faiss.py --backend hpo_node2vec_faiss
```

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

팀 배포는 GitHub Actions의 `Deploy to spare Mac` workflow에서 수동 실행한다. 자세한 절차는 `docs/github_actions_deployment.md`를 참고한다.

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
- `original_hpo_mapper`: 원본 `UoS-HGIG/HPO-Mapper`를 API로 감싼 외부 endpoint를 호출한다.
- `dictionary_doc2hpo`: dictionary와 Doc2HPO 결과를 병합한다.

프론트엔드 HPO extraction 선택지에는 `off`를 노출하지 않는다. Clinical note 입력에서는 `dictionary`를 기본값으로 사용하고, HPO를 직접 입력하려면 `HPO terms` 탭을 사용한다. API 호환성을 위해 `hpo_mapper="off"` 처리는 남겨두지만 사용자 화면의 기본 흐름에서는 제외한다.

`doc2hpo` 모드는 `.env`에 외부 endpoint를 설정해야 한다.

```text
RAREDX_DOC2HPO_URL=http://127.0.0.1:9000/map
RAREDX_ORIGINAL_HPO_MAPPER_URL=http://127.0.0.1:9001/map
RAREDX_DOC2HPO_TIMEOUT_SECONDS=20
```

외부 endpoint는 `POST` JSON 요청을 받아 HPO 후보 목록을 JSON으로 반환해야 한다. `doc2hpo` 모드가 지원하는 응답 key는 `extracted_phenotypes`, `hpo_terms`, `matches`, `results`, `mapped_terms` 중 하나다.

`original_hpo_mapper` 모드는 원본 `UoS-HGIG/HPO-Mapper`의 P1/P2/P3 개념을 보존하는 전용 adapter를 사용한다. RARE_DX_AI는 wrapper endpoint로 다음 형태의 JSON을 보낸다.

```json
{
  "clinical_note": "The patient has seizure and developmental delay.",
  "protocol": "p1",
  "top_k": 10,
  "max_hpo_terms": 30,
  "threshold": 0.76,
  "min_sim": 0.76,
  "embed_model": "nomic-embed-text",
  "embedding_model": "nomic-embed-text",
  "llm": {
    "enabled": false,
    "provider": "off",
    "chat_model": ""
  },
  "return_candidates": true
}
```

wrapper endpoint는 원본 HPO-Mapper CSV/JSON 결과를 다음 key 중 하나로 감싸서 반환하면 된다: `mapped_rows`, `mapped_terms`, `mapped`, `matches`, `results`, `predictions`, `extracted_phenotypes`, `hpo_terms`, `data`. 각 row는 원본 repo 출력에 가까운 `finding`, `region`, `hpo_id`, `hpo_term`, `matched_term`, `genes`, `score` 또는 `similarity` 필드를 사용하면 된다. `HP_0001250` 또는 `http://purl.obolibrary.org/obo/HP_0001250` 형태도 내부에서 `HP:0001250`로 정규화한다.

원본 HPO-Mapper를 로컬 FastAPI wrapper로 띄우려면 별도 터미널에서 다음처럼 실행한다. 큰 SQLite embedding DB와 HPO JSON은 git에 넣지 않고 로컬 경로만 `.env`에 지정한다.

원본 asset은 Hugging Face Space `UoS-HGIG/HPOmapper`에서 받을 수 있다.

```bash
mkdir -p data/external/original_hpo_mapper
curl -L --fail --continue-at - \
  --output data/external/original_hpo_mapper/hp.json \
  https://huggingface.co/spaces/UoS-HGIG/HPOmapper/resolve/main/hp.json
curl -L --fail --continue-at - \
  --output data/external/original_hpo_mapper/hpo_genes_with_synonyms.db \
  https://huggingface.co/spaces/UoS-HGIG/HPOmapper/resolve/main/hpo_genes_with_synonyms.db
```

```text
RAREDX_ORIGINAL_HPO_MAPPER_URL=http://127.0.0.1:9001/map
RAREDX_ORIGINAL_HPO_MAPPER_DB_PATH=/path/to/hpo_genes_with_synonyms.db
RAREDX_ORIGINAL_HPO_MAPPER_HPO_JSON=/path/to/hp.json
RAREDX_ORIGINAL_HPO_MAPPER_MAX_GENES=50
RAREDX_OLLAMA_URL=http://localhost:11434
```

`RAREDX_ORIGINAL_HPO_MAPPER_MAX_GENES`와 요청 option `max_genes`는 HPO 매핑 계산에 사용되지 않는다. 매핑은 clinical text embedding과 HPO synonym embedding의 cosine similarity로 결정되고, gene list는 매핑된 HPO term에 붙는 evidence payload다. 프론트 안정성을 위해 기본 preview는 50개이며, Original mapper option에서 50/100/1000/All로 조정할 수 있다. `gene_count`에는 전체 연결 gene 수가 보존된다.

```bash
ollama pull nomic-embed-text
uv run uvicorn app.original_hpo_mapper_wrapper:app --reload --port 9001
```

wrapper 상태 확인:

```bash
curl http://127.0.0.1:9001/health
```

프론트엔드는 `/api/hpo-mappers`에서 mapper 목록과 설정 가능한 option을 받아 UI를 렌더링한다. Original HPO-Mapper adapter는 protocol, LLM on/off, provider, top-k, threshold, model 설정을 요청별 option으로 전달한다.

Disease ranking option은 HPO mapper option과 별도로 관리한다.

```text
HPO extraction option
-> clinical note를 HPO term으로 바꾸는 앞단 설정
-> Doc2HPO threshold, candidate limit, LLM QC/selection 등

Disease ranking option
-> HPO term set으로 disease candidate를 정렬하는 뒷단 설정
-> disease embedding backend, hybrid weights, graph evidence mode 등
```

Ranking method capability는 다음 endpoint에서 확인할 수 있다.

```bash
curl http://127.0.0.1:8010/api/retrieval/ranking-methods
```

현재 disease embedding backend는 `sapbert_faiss`, `pubmedbert_faiss`, `biosentvec_faiss`, `custom_sentence_transformer_faiss`, `hpo_deepwalk_faiss`, `hpo_node2vec_faiss`를 지원한다.
`sapbert_faiss`는 SapBERT 고정 비교군이고, `pubmedbert_faiss`는 PubMedBERT 기반 biomedical literature encoder 비교군이다.
`biosentvec_faiss`는 BioSentVec 외부 모델 파일을 사용하는 sentence-vector 비교군이며, 모델 파일 경로와 optional `sent2vec` package 설정이 필요하다.
`custom_sentence_transformer_faiss`는 모델명을 직접 입력해 sentence-transformer 계열 embedding retrieval을 비교하는 실험용 backend다.
`hpo_deepwalk_faiss`와 `hpo_node2vec_faiss`는 `hp.obo`의 HPO `IS_A` ontology graph만 사용해 HPO node vector를 만든 뒤 FAISS로 disease profile을 검색하는 graph embedding backend다.
Neo4j에 적재된 disease-gene-phenotype 전체 knowledge graph가 아니라, HPO term 사이의 ontology DAG를 사용한다.
프론트는 `/api/retrieval/ranking-methods` capability에 내려오는 선택지를 자동으로 렌더링한다.

Graph evidence mode와 HPO graph embedding backend는 다른 층이다.

| 항목 | 위치 | 입력 | 목적 |
|---|---|---|---|
| `local_overlap`, `frequency_weighted_graph`, `gene_path`, `source_confidence_graph` | Graph evidence / Hybrid component | Patient HPO와 disease/gene/annotation evidence | 후보 disease의 graph evidence score 계산 |
| `hpo_deepwalk_faiss` | Disease embedding backend | HPO ontology `IS_A` graph의 uniform random walk | patient/disease vector similarity search |
| `hpo_node2vec_faiss` | Disease embedding backend | HPO ontology `IS_A` graph의 biased random walk | patient/disease vector similarity search |

LLM QC/selection은 mapper가 만든 HPO 후보를 검수하는 후처리 단계다. 새 HPO term을 생성하지 않고, 제공된 후보 HPO ID 중 유지할 항목만 고른다. OpenAI API를 우선 사용할 수 있고, 로컬 실험은 Ollama로 대체할 수 있다.

```text
RAREDX_LLM_PROVIDER=openai
OPENAI_API_KEY=...
RAREDX_OPENAI_MODEL=gpt-4o-mini

# local fallback
RAREDX_LLM_PROVIDER=ollama
RAREDX_OLLAMA_URL=http://localhost:11434
RAREDX_OLLAMA_CHAT_MODEL=phi4-mini
```

`extracted_phenotypes[].metadata`에는 mapper source, candidate rank, threshold, embedding model, LLM provider/model/protocol, QC status 같은 provenance가 포함된다. HPO ID/name/definition/evidence 같은 원천 지식과 달리, 이 metadata는 RARE_DX_AI가 생성하는 실행 추적 정보다.

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

현재 권한 모델은 팀원 7명을 모두 관리자/연구자로 두는 방식이다. 현재 화면은 팀 내부 연구/시연용 workspace로 사용하고, 향후 일반 사용자 또는 잠정 고객용 화면은 `Graph Explorer`로 분리해 완성한다. 관리자용 graph 점검 화면은 `Cypher Lab`으로 분리하고 Cloudflare Access에서 관리자 이메일만 허용한다.

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
