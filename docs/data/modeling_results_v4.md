# Disease–Gene Link Prediction — 모델링 결과 v4 (엣지 가중치 실험 + 뜻밖의 발견)

상태: `MODELING_V4_AGGR_FINDING_NOT_YET_DEFAULT`
실험일: 2026-10-22 / 팀 공유 준비일: 2026-10-22
브랜치: `feature/edge-weight-ablation` (`feature/multi-seed-reporting` 위에 쌓임, 그 위는 `feature/dg-link-prediction-modeling`)

v3(`docs/data/modeling_results_v3.md`)의 "다음 시도" 중 하나였던, `docs/data/modeling_handoff.md`의 ablation A/B/C 엣지 가중치 파일을 실제로 써보는 실험입니다. 결과적으로 **가중치 자체는 효과가 없었고**, 그 과정에서 **별개의, 더 큰 발견**(GraphConv의 sum 집계가 SAGEConv의 mean 집계보다 꽤 크게 낫다)을 했습니다.

## 먼저 확인: cold-start와는 무관합니다

A/B/C는 **이미 존재하는 ASSOCIATED_WITH 엣지에 가중치를 주는 것**이지, 그래프에 엣지가 아예 없는 cold-start 노드(이슈 #19)와는 무관합니다. 가중치를 아무리 잘 줘도 엣지가 0개인 노드는 여전히 0개입니다 — 이 실험은 cold-start 완화책이 아니라 순수히 메시지 패싱 "강도" 실험입니다.

## 인프라 (재사용 가능, 기본 동작은 변경 없음)

- `app/modeling/edge_weights.py`(신규): `load_ablation_weights(path)`가 ablation CSV를 `{(disease_id, gene_id): weight}` 딕셔너리로 읽고, `attach_associated_with_weights(data, node_indexes, weights)`가 `HeteroData`의 `ASSOCIATED_WITH`/`rev_ASSOCIATED_WITH` 엣지에 `edge_weight`를 붙입니다.
- `GNNLinkPredictor(..., associated_with_aggr="mean"|"sum")`(신규 파라미터, 기본값 `"mean"` = 기존 동작 그대로): `"sum"`일 때만 해당 두 관계가 `SAGEConv`(가중치 미지원) 대신 `GraphConv`(가중치 지원)를 씁니다. 다른 관계(IS_A, HAS_PHENOTYPE)는 항상 `SAGEConv`/mean 그대로입니다.
- `train_gnn`/`run_gnn_multi_seed`에 `associated_with_aggr` 그대로 전달. 둘 다 가중치를 직접 붙이진 않습니다 — 호출자가 `attach_associated_with_weights`로 미리 붙여야 합니다.
- `remove_dg_edges`(epoch별 supervision-holdout 누수 방지 로직)도 `edge_weight`가 있으면 `edge_index`와 같은 마스크로 같이 잘라내도록 수정 — 가중치가 있어도 학습 중 누수 방지는 그대로 작동합니다.
- **전부 하위 호환**: `associated_with_aggr` 기본값이 `"mean"`이라 기존 PR(#11, #18)의 모델/테스트는 전혀 영향받지 않습니다 (확인: `feature/multi-seed-reporting` 브랜치엔 이 코드 자체가 없음).

## 실험 1: A/B/C 가중치 비교 (seed 3개, real data)

| 설정 | val MRR |
|---|---:|
| unweighted (SAGEConv, 기존 기본값) | 0.0199 ± 0.0023 |
| A (evidence_score, GraphConv) | 0.0300 ± 0.0022 |
| B (train-only IDF, GraphConv) | 0.0256 ± 0.0033 |
| C (가중치 없음=1.0 전부, GraphConv) | 0.0295 ± 0.0008 |

**처음엔 "가중치가 효과 있다"로 보였지만 교란 요인이 있었습니다**: C는 "가중치 없음"이 아니라 "GraphConv + 가중치 전부 1"이라, `unweighted`(SAGEConv)와 비교하면 가중치 효과와 conv 종류 효과가 섞여버립니다. **conv 종류를 고정하고 가중치만 비교(A vs B vs C, 전부 GraphConv)하면 0.0300 / 0.0256 / 0.0295로 서로 noise 범위 안**입니다.

**결론 1: 증거 기반 가중치(A/B)가 균등 가중치(C)보다 낫다는 증거 없음.**

## 실험 2: SAGEConv(mean) vs GraphConv(sum) — 가중치 없이 conv 종류만 (seed 5개, real data, val+test)

파라미터 수가 완전히 동일함을 확인했습니다 (둘 다 8,256개, root weight + neighbor weight + bias 구조 동일) — 차이는 순수하게 평균 vs 합 집계뿐입니다.

| | val MRR | test MRR | val Hits@50 | test Hits@50 |
|---|---:|---:|---:|---:|
| SAGEConv (mean, 현재 기본값) | 0.0191 ± 0.0021 | 0.0170 ± 0.0024 | 0.0657 | 0.0694 |
| GraphConv (sum) | 0.0286 ± 0.0014 | 0.0305 ± 0.0029 | 0.1325 | 0.1398 |

5개 seed 전부에서 두 구간이 전혀 안 겹칩니다 (SAGEConv 최댓값 0.0219 < GraphConv 최솟값 0.0269). MRR 기준 50~80% 개선, Hits@50은 거의 2배 — noise로 설명하기 어렵습니다.

**결론 2: ASSOCIATED_WITH 관계만 sum 집계로 바꾸면(가중치 없이도) 꽤 크게 개선됩니다.** `app/modeling/models.py`에 원래 "mean이 hub gene degree skew를 눌러준다"는 가정으로 SAGEConv를 선택했다고 적어뒀는데, 실측 결과는 반대입니다 — gene의 연결 정도 자체가 유의미한 신호이고, sum이 그 신호를 더 잘 보존하는 것 같습니다.

## 아직 기본값으로 바꾸지 않은 이유

- ASSOCIATED_WITH 하나만 테스트했습니다. IS_A/HAS_PHENOTYPE도 sum으로 바꾸면 어떻게 되는지는 안 봤습니다.
- seed 5개는 양호하지만, v3에서 배운 교훈(단일/소수 seed 비교의 위험성)을 생각하면 이 정도 큰 차이도 한 번 더 다른 그래프 split(`--seed`)으로 교차검증해보는 게 이상적입니다.
- 이건 PR #11/#18에서 이미 리뷰를 받고 있는 모델 아키텍처의 핵심 설계 결정(SAGEConv 선택 근거)을 뒤집는 변경이라, 별도로 검토받는 게 맞다고 판단했습니다.

## 다음 단계 제안

1. `associated_with_aggr="sum"`을 기본값으로 승격할지 — 리뷰어 판단 필요.
2. 승격한다면, 다른 관계(IS_A/HAS_PHENOTYPE)도 sum으로 바꿔볼지 추가 실험.
3. A/B/C 가중치 자체는 추가 조사 가치가 낮아 보입니다(결론 1 참고) — 우선순위 낮음.

재현 코드: `app/modeling/edge_weights.py`, `GNNLinkPredictor.associated_with_aggr`. 실험 스크립트는 일회성이라 저장소에 남기지 않았습니다(본 문서가 기록).
