# Cloudflare Tunnel 기반 팀 공유 호스팅

이 문서는 남는 맥북에서 RARE_DX_AI를 실행하고, 팀원들이 도메인으로 FastAPI와 Neo4j Browser를 사용할 수 있게 공개하는 방법을 정리한다.

## 목표 구조

```text
팀원 브라우저
  -> Cloudflare 도메인
  -> Cloudflare Tunnel
  -> 남는 맥북
  -> FastAPI / Neo4j Browser
```

공개할 서비스:

```text
https://raredx-api.example.com   -> FastAPI, local port 8010
https://raredx-neo4j.example.com -> Neo4j Browser, local port 7474
```

Neo4j Bolt:

```text
bolt://localhost:7687
```

Bolt port `7687`은 일반 브라우저용 HTTP 서비스가 아니므로 Cloudflare Tunnel public hostname으로 직접 공개하지 않는 것을 기본으로 한다. 팀원이 Cypher를 실행하려면 Neo4j Browser를 통해 접속한다.

## 전제 조건

- 도메인이 Cloudflare에 연결되어 있어야 한다.
- 남는 맥북에 Docker Desktop이 실행 중이어야 한다.
- Neo4j 컨테이너가 실행 중이어야 한다.
- FastAPI 서버가 실행 중이어야 한다.

현재 로컬 실행 예:

```bash
docker compose up -d neo4j
uvicorn app.main:app --reload --port 8010
```

Neo4j local 접속:

```text
http://localhost:7474
Username: neo4j
Password: raredx_password
Database: neo4j
```

FastAPI local 접속:

```text
http://127.0.0.1:8010/docs
```

## Cloudflared 설치

macOS:

```bash
brew install cloudflare/cloudflare/cloudflared
```

Cloudflare 로그인:

```bash
cloudflared tunnel login
```

브라우저가 열리면 사용할 도메인을 선택한다.

## Tunnel 생성

```bash
cloudflared tunnel create raredx-ai
```

생성 후 tunnel ID가 출력된다. 예:

```text
Created tunnel raredx-ai with id <TUNNEL_ID>
```

## Tunnel 설정 파일

Cloudflared 설정 파일 위치:

```text
~/.cloudflared/config.yml
```

예시:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /Users/<YOUR_USER>/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: raredx-api.example.com
    service: http://localhost:8010
  - hostname: raredx-neo4j.example.com
    service: http://localhost:7474
  - service: http_status:404
```

바꿔야 할 값:

```text
<TUNNEL_ID>
<YOUR_USER>
raredx-api.example.com
raredx-neo4j.example.com
```

## DNS 연결

```bash
cloudflared tunnel route dns raredx-ai raredx-api.example.com
cloudflared tunnel route dns raredx-ai raredx-neo4j.example.com
```

## Tunnel 실행

```bash
cloudflared tunnel run raredx-ai
```

정상 실행되면 팀원은 다음 주소로 접근할 수 있다.

```text
https://raredx-api.example.com/docs
https://raredx-neo4j.example.com
```

## 팀원에게 공유할 접속 정보

FastAPI:

```text
https://raredx-api.example.com/docs
```

Neo4j Browser:

```text
https://raredx-neo4j.example.com
```

Neo4j 로그인:

```text
Username: neo4j
Password: raredx_password
Database: neo4j
```

## Cloudflare Access 권장 설정

그래프 DB에 개인 민감 데이터가 없더라도, Neo4j Browser는 쿼리를 직접 실행할 수 있으므로 팀원만 접근하도록 제한하는 것이 좋다.

권장:

```text
raredx-api.example.com   -> 팀원 이메일만 허용
raredx-neo4j.example.com -> 팀원 이메일만 허용
```

Cloudflare Dashboard에서 설정:

```text
Zero Trust
-> Access
-> Applications
-> Add an application
-> Self-hosted
```

Application 예시:

```text
Name: RARE_DX_AI API
Domain: raredx-api.example.com
Policy: Allow team emails
```

```text
Name: RARE_DX_AI Neo4j
Domain: raredx-neo4j.example.com
Policy: Allow team emails
```

팀원 이메일만 허용:

```text
Include -> Emails -> team-member@example.com
```

또는 같은 도메인 이메일을 쓰면:

```text
Include -> Emails ending in -> @example.com
```

## 맥북이 꺼지지 않게 설정

호스팅용 맥북은 잠자기 모드에 들어가면 접속이 끊긴다.

임시 실행:

```bash
caffeinate -dimsu
```

또는 시스템 설정에서:

```text
System Settings
-> Displays / Battery / Lock Screen
-> 전원 연결 시 sleep 방지
```

## 운영 중 확인 명령어

Neo4j 상태:

```bash
docker compose ps
```

Neo4j count 확인:

```bash
docker exec raredx-neo4j cypher-shell -u neo4j -p raredx_password \
  "MATCH (n) RETURN labels(n), count(n) LIMIT 10;"
```

FastAPI 확인:

```bash
curl http://127.0.0.1:8010/openapi.json
```

Tunnel 확인:

```bash
cloudflared tunnel list
```

## 주의사항

- Neo4j Browser는 Cypher query를 직접 실행할 수 있으므로 public open 상태로 두지 않는 것이 좋다.
- 최소한 Cloudflare Access로 팀원 이메일 제한을 건다.
- 현재 Neo4j password는 개발용 기본값이므로, 실제 공유 전에는 바꾸는 것이 좋다.
- 팀원이 동시에 무거운 전체 그래프 쿼리를 실행하면 맥북과 Neo4j가 느려질 수 있다.
- 전체 그래프 조회는 피한다.

피해야 할 쿼리:

```cypher
MATCH (n)-[r]-(m)
RETURN n, r, m
```

대신 항상 조건과 제한을 둔다.

```cypher
MATCH (d:Disease)-[r:HAS_PHENOTYPE]->(p:Phenotype {id: "HP:0001250"})
RETURN d, r, p
LIMIT 50;
```
