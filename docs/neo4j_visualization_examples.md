# Neo4j 시각화 예제

RARE_DX_AI의 Disease-Gene-Phenotype knowledge graph는 Neo4j Browser에서 바로 시각화할 수 있다.

## 접속 정보

Neo4j Browser:

```text
http://localhost:7474
```

로그인:

```text
Username: neo4j
Password: raredx_password
Database: neo4j
```

## 현재 그래프 규모

현재 로컬 Neo4j에 적재된 그래프 규모:

```text
Disease nodes: 13028
Phenotype nodes: 19855
Gene nodes: 5273
Relationships: 592771
```

전체 그래프가 크기 때문에 항상 `WHERE` 조건과 `LIMIT`를 걸어서 조회한다.

피해야 할 쿼리:

```cypher
MATCH (n)-[r]-(m)
RETURN n, r, m
```

이런 전체 그래프 조회는 너무 많은 node와 relationship을 반환할 수 있다.

## 1. 특정 HPO term과 연결된 disease 보기

예시 HPO:

```text
HP:0001250 = Seizure
```

Cypher:

```cypher
MATCH (d:Disease)-[r:HAS_PHENOTYPE]->(p:Phenotype {id: "HP:0001250"})
RETURN d, r, p
LIMIT 50;
```

확인할 점:

- 어떤 disease들이 `Seizure` phenotype과 연결되어 있는지 볼 수 있다.
- `HAS_PHENOTYPE` relationship의 `frequency`, `evidence`, `source` 속성을 확인할 수 있다.

## 2. 여러 HPO term을 동시에 가진 disease 보기

예시 HPO:

```text
HP:0001250 = Seizure
HP:0001263 = Global developmental delay
```

Cypher:

```cypher
MATCH (d:Disease)-[r1:HAS_PHENOTYPE]->(p1:Phenotype {id: "HP:0001250"})
MATCH (d)-[r2:HAS_PHENOTYPE]->(p2:Phenotype {id: "HP:0001263"})
RETURN d, r1, p1, r2, p2
LIMIT 50;
```

확인할 점:

- 두 phenotype을 모두 가진 disease 후보를 볼 수 있다.
- IC baseline이나 graph retrieval 결과를 눈으로 검증할 때 유용하다.

## 3. Disease-Gene-Phenotype path 보기

예시 HPO:

```text
HP:0001250 = Seizure
```

Cypher:

```cypher
MATCH path = (p:Phenotype {id: "HP:0001250"})<-[:HAS_PHENOTYPE]-(d:Disease)-[:ASSOCIATED_WITH]->(g:Gene)
RETURN path
LIMIT 50;
```

확인할 점:

- 특정 phenotype과 연결된 disease를 찾고, 그 disease와 연결된 gene까지 볼 수 있다.
- 설명 가능한 evidence path를 확인할 때 유용하다.

그래프 해석:

```text
Phenotype <- Disease -> Gene
```

프로젝트 설명에서는 환자 phenotype을 기준으로 다음처럼 표현할 수 있다.

```text
Patient -> Phenotype -> Disease -> Gene
```

## 4. 특정 disease 중심으로 주변 그래프 보기

예시 disease:

```text
OMIM:312750
```

Cypher:

```cypher
MATCH path = (d:Disease {id: "OMIM:312750"})-[*1..2]-(n)
RETURN path
LIMIT 100;
```

확인할 점:

- 특정 disease와 직접 또는 2-hop 이내로 연결된 phenotype/gene을 볼 수 있다.
- disease profile이 어떤 phenotype set으로 구성되어 있는지 확인할 수 있다.

주의:

- `[*1..2]`는 2-hop 경로까지 확장하므로 결과가 많아질 수 있다.
- 필요하면 `LIMIT`를 더 작게 줄인다.

## 5. 여러 phenotype에서 gene까지 포함해 보기

예시 HPO:

```text
HP:0001250 = Seizure
HP:0001263 = Global developmental delay
HP:0000252 = Microcephaly
```

Cypher:

```cypher
MATCH path = (p:Phenotype)<-[:HAS_PHENOTYPE]-(d:Disease)-[:ASSOCIATED_WITH]->(g:Gene)
WHERE p.id IN ["HP:0001250", "HP:0001263", "HP:0000252"]
RETURN path
LIMIT 100;
```

확인할 점:

- 입력 phenotype set과 관련된 disease-gene 연결을 함께 볼 수 있다.
- retrieval 결과의 graph evidence를 시각적으로 확인할 수 있다.

## 6. 특정 disease의 phenotype만 보기

Cypher:

```cypher
MATCH (d:Disease {id: "OMIM:312750"})-[r:HAS_PHENOTYPE]->(p:Phenotype)
RETURN d, r, p
LIMIT 100;
```

확인할 점:

- disease가 어떤 HPO term들과 annotation되어 있는지 확인할 수 있다.
- `frequency` 값이 있으면 해당 phenotype이 disease에서 얼마나 자주 나타나는지 볼 수 있다.

## 7. 특정 gene과 연결된 disease/phenotype 보기

예시 gene:

```text
MECP2
```

Cypher:

```cypher
MATCH path = (g:Gene {symbol: "MECP2"})--(n)
RETURN path
LIMIT 100;
```

더 넓게 disease와 phenotype까지 보고 싶으면:

```cypher
MATCH path = (g:Gene {symbol: "MECP2"})--(d:Disease)-[:HAS_PHENOTYPE]->(p:Phenotype)
RETURN path
LIMIT 100;
```

확인할 점:

- 특정 gene이 어떤 disease와 연결되어 있는지 볼 수 있다.
- gene-disease-phenotype evidence를 함께 확인할 수 있다.

## Notion 공유용 요약

RARE_DX_AI의 Neo4j graph는 disease, phenotype, gene node로 구성된다.

주요 관계:

```text
Disease - HAS_PHENOTYPE -> Phenotype
Disease - ASSOCIATED_WITH -> Gene
Gene - ASSOCIATED_PHENOTYPE -> Phenotype
```

시각화 목적:

- 입력 HPO term과 연결된 disease 후보 확인
- disease와 연결된 gene 확인
- candidate ranking 결과의 graph evidence 검증
- 설명 가능한 path 확인

주의:

- 전체 그래프 조회는 피한다.
- 항상 `WHERE`와 `LIMIT`를 사용한다.
- 시각화 결과는 진단 근거가 아니라 candidate prioritization을 위한 graph evidence로 해석한다.

