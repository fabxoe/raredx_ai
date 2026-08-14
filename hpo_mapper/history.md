# HPO Mapper Development History

이 문서는 `HPO Mapper` 개발 과정을 기록하기 위한 히스토리 문서입니다.

> 주의: 이 문서는 `HPO_Disease_Mapping`과 별개의 프로젝트/작업 기록입니다.
> 두 작업은 서로 다른 목적과 개발 흐름을 갖고 있으므로 혼동하지 않습니다.

## 1. 개요

- 프로젝트: HPO Mapper 개발
- 목적: 임상 note 기반으로 phenotype phrase를 추출하고, 이를 HPO term으로 매핑하는 파이프라인을 개발
- 구분: HPO Mapper는 질환-질병 매핑(`HPO_Disease_Mapping`)과 다릅니다. HPO Mapper는 `phenotype -> HPO` 변환과 평가를 목표로 합니다.

## 2. 데이터셋 준비 (현재 진행 전)

이 섹션은 평가용 `Gold HPO` 데이터셋 준비를 위한 기록 자리입니다.

### 2.1 현재 상태

- `rarearena_rdc_sample_1000.csv`를 기반으로 Gold HPO 평가용 샘플 생성 작업이 필요함
- 아직 수작업 Gold HPO annotation은 시작하지 않음
- 현재까지 수행된 작업:
  - 데이터 파일 존재 여부 확인
  - `patient_id`, `clinical_note`, `Orpha_name` 컬럼 존재 여부 확인
  - 데이터 분포 및 note 길이 분석
  - 층화 샘플링 기반 100건 추출 로직 구현

### 2.2 향후 작업 항목

- [ ] 수작업 Gold HPO annotation을 위한 dataset A/B 준비 완료
- [ ] `gold_hpo_ids` 칼럼에 수작업 값을 입력할 준비
- [ ] annotation 지침 문서 작성
- [ ] dataset 품질 검증 및 검수 절차 수립

### 2.3 데이터셋 기록 템플릿

- 데이터 파일: `data/processed/rarearena_rdc_sample_1000.csv`
- 추출일: YYYY-MM-DD
- 샘플 수: 100개 (A 50개, B 50개)
- 포함 컬럼: `patient_id`, `clinical_note`, `Orpha_name`, `gold_hpo_ids`
- 샘플링 기준:
  - `clinical_note` 길이 기반 `Short` / `Medium` / `Long` 균형
  - `Orpha_name` 다양성 우선
  - `patient_id` 중복 없음

## 3. HPO Mapper 개발 계획

이 섹션은 HPO Mapper 자체 개발 로드맵과 기록을 위한 공간입니다.

### 3.1 목표

- Clinical Note에서 phenotype phrase를 안정적으로 추출
- 추출된 phrase 각각에 대해 HPO term을 매핑
- multi-phenotype HPO set을 생성하여 downstream 활용성 확보

### 3.2 주요 개발 단계

1. **Baseline 정리**
   - 기존 `mapper (1).py` 기반 구성 요소 확인
   - baseline 설정, 하이퍼파라미터 기록

2. **Phenotype Phrase Extraction 개선**
   - 임상 note를 문장/구문 단위로 분리
   - symptom/phenotype phrase 후보 추출
   - 불필요 구문 제거 및 정제

3. **Context Filtering**
   - 부정 표현(`negation`) 처리
   - 가족력(`family history`) 및 과거력(`historical`) 분리
   - 현재 증상만 HPO mapping에 반영

4. **Semantic Similarity 기반 HPO Mapping**
   - phrase별 embedding 생성
   - HPO term embedding과 유사도 검색
   - Top-K/threshold 기반 후보 선정
   - 중복/상위어 필터링

5. **Ontology-aware 후처리**
   - HPO 계층 구조를 이용한 ancestor/descendant 중복 제거
   - 표현의 세부성에 따른 term 선택 전략

6. **평가셋 구축 및 검증**
   - Gold HPO annotation dataset 구축
   - phenotype 추출 평가와 HPO 매핑 평가 구분
   - 정확도, 재현율, F1, 오탐/누락 분석

### 3.3 개발 기록 템플릿

#### 실험 기록

- 날짜:
- 코드 버전 / 파일:
- 사용 데이터셋:
- 노트 수:
- 추출 방식:
- 매핑 전략:
- `top_k`:
- `threshold`:
- `gold_hpo_ids` 처리:
- 결과 요약:

#### 평가 결과

- Phenotype Detection
  - Precision:
  - Recall:
  - F1:
- HPO Mapping
  - Exact Match:
  - Ancestor/Descendant Match:
  - Wrong Mapping:
  - Over-specific Mapping:
  - Under-specific Mapping:

#### 관찰 및 개선 사항

- 주요 오류 패턴:
- 개선 방안:
- 다음 작업:

## 4. 추가 참고

- 현재 `HPO Mapper`의 목표는 `HPO_Disease_Mapping`과 다른 `phenotype -> HPO` 변환 과정임
- 두 프로젝트가 동일한 HPO 용어를 사용할 수는 있으나, 개발 목적과 평가 지표는 다름
- 본 파일에는 HPO Mapper 프로세스와 데이터셋 준비 기록을 함께 남김
