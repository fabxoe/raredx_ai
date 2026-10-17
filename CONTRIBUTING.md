# Contributing

## 개발 흐름

1. 최신 `main`에서 짧게 유지할 작업 브랜치를 만듭니다.
2. 기능이나 버그를 설명하는 이슈를 연결합니다.
3. 변경 범위에 맞는 테스트와 문서를 함께 수정합니다.
4. Pull Request를 `main`으로 열고 CI와 리뷰를 통과한 뒤 병합합니다.

브랜치 이름은 `feature/`, `fix/`, `refactor/`, `docs/`, `chore/` 접두사를 권장합니다.

## 개발 환경과 검증

Python 3.12와 `uv`를 기준으로 합니다.

```bash
uv sync --locked --extra dev
uv run pytest -q
docker compose config
```

프로젝트 커밋 템플릿을 사용하려면 clone마다 다음 명령을 한 번 실행합니다.

```bash
git config commit.template .github/commit_template.txt
```

## 구현 원칙

- retrieval은 후보 생성과 검색을 담당하며 LLM을 직접 호출하지 않습니다.
- graph는 Neo4j 조회, 경로 추출과 근거 수집을 담당합니다.
- reranking은 IC, graph, embedding 점수를 결합해 점수가 포함된 후보 목록을 반환합니다.
- LLM은 구조화된 근거를 바탕으로 설명하며 근거를 만들어내지 않습니다.
- 후보 질환에는 matching phenotypes, missing phenotypes, associated genes와 graph path evidence를 제공합니다.
- 제한된 임상 데이터 규모에서 재현 가능하고 해석 가능한 방법을 우선합니다.

새 추상화, 계층, 상태 모델, 캐시 또는 인프라를 추가할 때는 현재 구조로 해결하기 어려운 이유와 유지보수 비용을 PR에 기록합니다.

## 데이터와 보안

- 실제 환자 개인정보와 원본 의료문서를 이슈, PR, fixture, 로그에 올리지 않습니다.
- 비밀정보와 `.env` 파일을 커밋하지 않습니다.
- 큰 데이터셋, 생성된 인덱스와 모델 파일은 Git으로 관리하지 않습니다.
- 외부 데이터의 출처, 버전과 라이선스를 기록합니다.

보안 취약점은 공개 이슈 대신 [Security Policy](SECURITY.md)의 절차로 보고합니다.
