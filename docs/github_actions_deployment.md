# GitHub Actions 테스트 및 Windows 배포 운영 가이드

## 기본 흐름

```text
PR 생성 또는 main push
-> GitHub-hosted CI 실행
-> 테스트와 설정 검증 통과
-> 승인 및 main 병합
-> Deploy to Windows server 수동 실행
-> Windows 서버에서 코드 업데이트, 테스트, 서비스 재시작 및 상태 확인
```

## CI Action

`CI` workflow는 `pull_request`와 `main` push에서 자동 실행된다.

검증 항목:

- `uv sync --locked --extra dev`
- `uv run pytest -q`
- `docker compose config`
- `.env`가 Git에 tracked 되어 있는지 검사
- tracked 파일에 OpenAI API key 패턴이 들어갔는지 검사

CI는 GitHub-hosted `ubuntu-latest`에서 실행된다. 공개 저장소의 PR 코드는
self-hosted Windows runner에서 실행하지 않는다.

## 수동 Windows 배포

배포 workflow 이름은 `Deploy to Windows server`이다.

1. GitHub repository의 `Actions` 탭으로 이동한다.
2. `Deploy to Windows server`를 선택한다.
3. `Run workflow`를 누른다.
4. branch가 `main`인지 확인하고 실행한다.
5. 로그에서 테스트 통과와 각 HTTP 상태 확인을 검토한다.

배포 workflow는 `workflow_dispatch`로만 실행되며 동시 배포를 허용하지 않는다.
러너에는 `raredx-windows` label이 필요하다.

## Windows 서버 구성

- 저장소: `C:\raredx\app`
- 서버 환경 파일: `C:\raredx\app\.env`
- Python 환경: `C:\raredx\app\.venv`
- 시스템 uv: `C:\Program Files\uv\uv.exe`
- Neo4j: 네이티브 Windows 서비스 `neo4j`
- FastAPI: 예약 작업 `RareDX-App`, `127.0.0.1:8010`
- GitHub Actions Runner: Windows 서비스, label `raredx-windows`

`scripts/windows/deploy.ps1`은 다음 작업을 수행한다.

- `main` 브랜치 fast-forward 업데이트
- UTF-8 모드에서 `uv sync --locked --python 3.12 --extra dev`
- 전체 pytest 실행
- Neo4j Windows 서비스와 HTTP 상태 확인
- `RareDX-App` 예약 작업 재시작
- 메인 앱과 mapper registry HTTP 상태 확인

`.env`와 데이터 파일은 Git에 커밋하지 않는다. OpenAI API key가 필요한 경우에도
GitHub Secrets가 아닌 서버의 `.env`에만 저장한다. Neo4j와 FastAPI는 loopback
주소에만 바인딩하고 외부 접근은 별도 인증 프록시를 통한다.

## 실패 시 확인

- GitHub Actions 실행 로그
- `Get-Service neo4j`
- `Get-Service 'actions.runner.*'`
- `Get-ScheduledTask -TaskName RareDX-App`
- `Invoke-WebRequest http://127.0.0.1:7474/`
- `Invoke-WebRequest http://127.0.0.1:8010/`

OpenAI credit 또는 API key 문제가 있어도 기본 서버는 내려가지 않아야 한다.
해당 기능 요청은 명시적인 오류 응답을 반환해야 한다.
