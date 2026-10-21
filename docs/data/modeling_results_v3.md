# Disease–Gene Link Prediction — 모델링 결과 v3 (DistMult + 재튜닝)

상태: `MODELING_V3_DISTMULT_RETUNED`
학습·평가일: 2026-10-21 / 팀 공유 준비일: 2026-10-21
브랜치: `feature/dg-link-prediction-modeling` (PR [#11](https://github.com/fabxoe/raredx_ai/pull/11))

v2(`docs/data/modeling_results_v2.md`)에서 early stopping + weight decay + 작은 GNN(dim=32)으로 과적합을 줄였습니다. 이번엔 디코더 자체를 더 가볍게 바꾸고, 그 변화에 맞춰 하이퍼파라미터를 다시 찾았습니다.

## 전달 방식

- 별도 Drive 폴더: [05.07_ai_modeling-ai 모델링](https://drive.google.com/drive/folders/1bMJLq-aQhGafGkd2u2BjP6CtbmJ4ndpU) 아래 새 하위 폴더 [Modeling_Results_v3_2026-10-21](https://drive.google.com/drive/folders/1w8QI362SaNkzXiq7bCtEllf4z7kWnstJ)에 업로드 완료: `dg_link_prediction_report_v6_final.json`, `baseline_state_dict.pt`, `gnn_state_dict.pt`.

## v2 대비 변경 사항

- **디코더: full bilinear → DistMult**. `BaselineScorer`/`GNNLinkPredictor` 둘 다 `disease_emb @ W @ gene_emb`(`embedding_dim²`개 파라미터)를 `sum(disease_emb * relation_weight * gene_emb)`(`embedding_dim`개 파라미터, 대각 관계 벡터)로 교체. Stanford CS224W류 지식그래프 임베딩 기법 중 하나로, 파라미터를 구조적으로 줄여 과적합을 억제하려는 시도입니다.
- **GNN `hidden_dim`/`embedding_dim`: 32 → 64로 복귀**. 디코더가 가벼워지니 노드 임베딩 자체는 다시 64차원이 더 잘 맞았습니다 — 실제 데이터로 grid sweep해서 확인했습니다.
- **CLI 기본값: `--epochs 150→400`, `--patience 15→20`**. baseline이 150 epoch로는 한참 덜 학습된 상태였고(epoch 287 근방에서야 수렴), DistMult 교체 이후 더 두드러졌습니다.

## 재현 방법

```bash
git checkout feature/dg-link-prediction-modeling
uv sync --extra dev
uv run python scripts/train_dg_link_model.py \
  --graph-dir data/processed/graph \
  --seed 42 \
  --output reports/dg_link_prediction_report.json \
  --model-dir reports/models
# (--epochs/--patience/--weight-decay 등은 이제 CLI 기본값 그대로 두면 됩니다)
```

## 결과 비교 (validation/test, combined)

| 모델 | Split | 지표 | v2 | v3 | 배율 |
|---|---|---|---:|---:|---:|
| baseline | validation | MRR | 0.0018 | **0.0125** | ×7.0 |
| baseline | test | MRR | 0.0022 | **0.0118** | ×5.4 |
| gnn | validation | MRR | 0.0187 | **0.0199** | ×1.1 |
| gnn | validation | Hits@50 | 0.0904 | **0.0813** | ×0.9 |
| gnn | test | MRR | 0.0158 | **0.0182** | ×1.2 |
| gnn | test | Hits@50 | 0.0868 | **0.0842** | ×1.0 |

**학습 길이**: baseline은 epoch 307에서 멈췄습니다(최적 epoch 287) — v2의 고정 150 epoch로는 수렴 전이었다는 뜻입니다. GNN은 epoch 97에서 멈췄습니다(최적 epoch 77).

**솔직한 평가**: baseline이 크게 좋아졌고(v2에서 "덜 학습됐다"는 지적이 맞았던 셈), GNN은 소폭 개선됐습니다. 다만 GNN의 Hits@50은 오히려 살짝 내려갔습니다 — MRR은 올랐지만 "상위 몇 개 안에 정답이 있는 비율" 자체는 지표별로 트레이드오프가 있다는 뜻으로, 완전한 승리는 아닙니다. GNN이 baseline보다 여전히 우위지만(MRR 기준 약 1.6배, v2의 8~9배보다는 격차가 줄었습니다 — baseline 자체가 훨씬 강해졌기 때문).

## 시도했다가 되돌린 것

- **Cold-start 공유 fallback 임베딩**: 그래프에 엣지가 전혀 없는 노드에 학습 가능한 공유 벡터를 대신 쓰는 방식을 시도했으나, 실제 데이터에서 cold-start 지표가 거의 안 움직였고 전체 지표는 오히려 나빠져서 되돌렸습니다. Cold-start는 여전히 구조적 한계로 남아있습니다(gene 쪽 약 40%).

## 읽는 법 / 주의사항

v1(`docs/data/modeling_results_v1.md`), v2 문서의 "읽는 법" 섹션이 그대로 적용됩니다. 체크포인트의 파라미터 이름이 `bilinear_weight` → `relation_weight`로 바뀌었으니, 과거 체크포인트(v1/v2)와 이번 체크포인트는 서로 `load_state_dict` 호환이 안 됩니다.

재현 코드·정책: 이 브랜치의 `app/modeling/`, `docs/superpowers/specs/2026-10-21-dg-link-prediction-modeling-design.md`.
