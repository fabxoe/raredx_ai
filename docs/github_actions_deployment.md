# GitHub Actions 테스트 및 배포 운영 가이드

이 문서는 RARE_DX_AI 팀원이 GitHub Actions로 테스트 결과를 확인하고, 남는 맥북 서버에 수동 배포하는 절차를 정리한다.

## 기본 흐름

```text
PR 생성 또는 main push
-> CI Action 실행
-> 테스트와 설정 검증 통과 확인
-> main 반영 후 Deploy to spare Mac Action 수동 실행
-> 남는 맥북에서 git pull, 테스트, Neo4j 확인, FastAPI 재시작
```

## CI Action

`CI` workflow는 `pull_request`와 `main` push에서 자동 실행된다.

검증 항목:

- `uv sync --locked --extra dev`
- `uv run pytest -q`
- `docker compose config`
- `.env`가 Git에 tracked 되어 있는지 검사
- tracked 파일에 OpenAI API key 패턴이 들어갔는지 검사

CI는 GitHub-hosted `ubuntu-latest`에서 실행된다. public repo의 PR 테스트에서 남는 맥북 self-hosted runner를 사용하지 않는다.

## 수동 배포 Action

배포 workflow 이름은 `Deploy to spare Mac`이다.

실행 방법:

1. GitHub repository의 `Actions` 탭으로 이동한다.
2. 왼쪽 workflow 목록에서 `Deploy to spare Mac`을 선택한다.
3. `Run workflow`를 누른다.
4. branch가 `main`인지 확인하고 실행한다.
5. 로그에서 `main app OK`, `mapper registry OK`, `original mapper wrapper OK`를 확인한다.

배포 중 수행하는 작업:

- 남는 맥북의 `~/workbench/raredx_ai`에서 `main` 최신 코드를 받는다.
- `uv sync --locked --python 3.12 --extra dev`를 실행한다.
- `uv run pytest -q`를 실행한다.
- Docker daemon과 Neo4j health를 확인한다.
- `app.main:app`을 `127.0.0.1:8010`에서 재시작한다.
- `app.original_hpo_mapper_wrapper:app`을 `127.0.0.1:9001`에서 재시작한다.

## Self-hosted Runner 요구사항

남는 맥북의 runner에는 `raredx-macbook` label이 필요하다.

남는 맥북에는 다음 리소스가 로컬에 있어야 한다.

- `~/workbench/raredx_ai/.env`
- `~/workbench/raredx_ai/data/raw`
- `~/workbench/raredx_ai/data/processed`
- `~/workbench/raredx_ai/data/external/original_hpo_mapper`
- Docker Desktop 또는 Docker daemon
- uv

OpenAI API key는 GitHub Secrets에 넣지 않는다. 서버 실행에 필요한 key는 남는 맥북의 `.env`에만 둔다.

## 실패 시 확인 위치

- GitHub Actions 실행 로그
- 남는 맥북의 `/tmp/raredx_app.log`
- 남는 맥북의 `/tmp/raredx_wrapper.log`
- Docker 상태:

```bash
docker compose ps
docker info
```

OpenAI credit 또는 API key 문제가 있어도 서버가 내려가지는 않아야 한다. 해당 기능 요청은 503 에러 메시지로 반환된다.

## 원복 방법

GitHub Actions 사용을 중단하려면 다음 파일들을 제거하면 된다.

```text
.github/workflows/ci.yml
.github/workflows/deploy-spare-mac.yml
```

남는 맥북 runner까지 제거하려면 GitHub repository Settings의 self-hosted runner 등록을 삭제하고, 남는 맥북의 runner 서비스를 중지한다.
