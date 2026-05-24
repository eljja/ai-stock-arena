# AI Stock Arena 진행 현황 및 비판적 검토

작성일: 2026-05-19 KST
대상 폴더: `D:\Codex`
검토 범위: 로컬 저장소, 로컬 SQLite DB, 공개 API 상태, 최근 문서와 핵심 코드

## 1. 한 줄 요약

이 폴더는 **LLM 모델들이 동일한 시장 데이터, 뉴스, 수수료, 포트폴리오 규칙 아래에서 가상 주식 매매를 수행하도록 하는 공개 벤치마크 서비스**를 구현하고 있다. 단순 데모를 넘어 FastAPI, Streamlit 대시보드, 스케줄러, OpenRouter 모델 관리, 뉴스 수집, Oracle 배포 스크립트까지 갖춘 상태다.

다만 현재 상태는 아직 "투자 성과를 검증한 서비스"라기보다 **운영 가능한 실험 장치**에 가깝다. 상업적 또는 학문적 가치가 생기려면 수익률 랭킹보다 먼저 데이터 출처, 재현성, 비교군, 위험 조정 지표, 모델 실패율, 규제 리스크를 정리해야 한다.

## 2. 현재 진행된 내용

### 제품/서비스 관점

- 공개 사이트: `https://aistockarena.com`
- 공개 API: `https://aistockarena.com/api`
- 목적: 여러 LLM 모델을 KR/US 시장에서 동일 조건으로 가상 운용시키고, 성과와 매매 판단을 비교한다.
- 현재 리그 초점: OpenRouter 무료/실험 모델 중심의 안정화 단계.
- 제공 화면/데이터: 랭킹, 포트폴리오, 포지션, 거래 내역, 성과 스냅샷, 뉴스, LLM 입력/출력 로그, copy-trade 형태의 현재 비중 API.

### 구현된 주요 구성

- API: `src/app/api/main.py`, `src/app/api/query_service.py`
- 대시보드: `src/app/dashboard/main.py`
- 스케줄러: `src/app/services/runtime_scheduler.py`
- LLM 호출: `src/app/llm/openrouter.py`
- 매매 루프: `src/app/orchestration/trading_cycle.py`
- 가상 체결/회계: `src/app/trading/engine.py`, `src/app/trading/costs.py`
- 시장 데이터: `src/app/market_data/provider.py`, `src/app/market_data/screener.py`
- 뉴스 수집: `src/app/news/*`, `src/app/services/shared_news.py`
- 운영 문서: `README.md`, `docs/runtime-admin-guide.md`, `docs/step-03-oracle-deployment.md`
- 배포: Oracle Cloud VM, systemd, nginx, watchdog, logrotate 스크립트.

### 로컬 DB 상태

로컬 `ai_stock_arena.db`는 약 27 MB이며 다음 데이터가 남아 있다.

- LLM 모델: 28개
- 포트폴리오: 29개
- 포지션: 67개
- 거래: 170건
- LLM 의사결정 로그: 143건
- 실행 요청: 152건
- 시간별 시장 가격: 81,626건
- 공유 뉴스 아이템: 16건

로컬 DB의 최신 거래/스냅샷은 2026-03-30에 멈춰 있다. 즉 로컬 DB는 현재 공개 서비스의 최신 상태를 반영하지 않는다.

### 공개 배포 상태

2026-05-18 UTC 기준 공개 API는 응답한다.

- `/api/health`: 정상
- `/api/overview?selected_only=true`: 선택 모델 32개, 포트폴리오 64개, 최신 거래 2026-05-18T15:24:43Z
- `/api/scheduler-status`: KR/US 모두 최근 실행은 `partial`
- KR 최근 실행: 17개 성공, 15개 실패, 후보 22개
- US 최근 실행: 17개 성공, 15개 실패, 후보 17개
- 랭킹 값은 존재하지만 `composite_score`는 대부분 0 또는 null이다.

이 차이는 중요하다. 저장소는 배포와 연결된 운영 자산을 갖고 있지만, 로컬 DB만 보고 현재 서비스를 판단하면 잘못된 결론이 나온다.

## 3. 현재 강점

### 이미 "살아 있는 시스템"이다

단순 백테스트 노트북이 아니라, 장기 실행 서비스 형태로 API, 대시보드, 스케줄러, 모델 discovery, 뉴스 수집, 포트폴리오 회계, 운영 스크립트가 이어져 있다. 이 자체가 좋은 출발점이다.

### 비교 실험의 기본 골격이 있다

모든 모델이 같은 후보군, 같은 뉴스, 같은 수수료, 같은 포트폴리오 규칙을 본다는 원칙이 문서와 코드에 반영되어 있다. 학문적 가치가 생기려면 이 원칙을 더 엄격하게 만들면 된다.

### 판단 로그가 남는다

`llm_decision_logs`에 프롬프트, 입력 payload, raw output, parsed output이 저장된다. 이는 단순 수익률 서비스가 아니라 LLM 행동 분석 데이터셋으로 확장할 수 있는 핵심 자산이다.

### 공개 API 형태가 좋다

랭킹, 포지션, 거래, 가격 이력, 실행 상태, copy-trade 형태의 비중 데이터를 읽기 전용 API로 제공한다. 외부 연구자나 앱이 붙을 수 있는 표면이 이미 있다.

## 4. 부족한 부분과 문제점

### 4.1 벤치마크 신뢰도가 아직 낮다

현재 랭킹은 raw return 중심이다. 그런데 각 모델의 운용 시작 시점, 거래 수, 실패율, 활성 기간이 다르면 단순 수익률 비교는 공정하지 않다.

특히 공개 API에서 일부 모델은 거래 수가 수백 건이고, 일부 모델은 0~10건 수준이다. 같은 표에 놓으면 신규 모델과 오래 돈 모델이 섞이고, 시장 regime 차이까지 함께 섞인다.

필요한 보정:

- 동일 시작일 cohort 랭킹
- 최소 거래 수/최소 운용일 기준
- 시장 벤치마크 대비 초과수익률
- 위험 조정 수익률
- 모델 실패율을 성과에 반영
- survivorship bias 제거

### 4.2 성과 지표가 미완성이다

코드상 `PerformanceSnapshot`에는 volatility, Sharpe ratio, composite score, average holding hours가 있지만 `src/app/trading/engine.py`에서 현재 0.0으로 기록된다.

이 상태에서 `config/defaults.toml`에 scoring weight가 있어도 실제 랭킹 품질에는 반영되지 않는다. 현재의 `composite_score`는 의사결정에 쓸 수 있는 지표가 아니다.

우선순위가 높은 수정:

- daily return 계산
- rolling volatility 계산
- Sharpe/Sortino 계산
- max drawdown 검증
- turnover penalty 반영
- composite score 산식 문서화 및 API 노출

### 4.3 실행 현실성이 부족하다

현재 가상 매매 엔진은 체결을 단순화한다.

- 시장가 체결만 가정
- slippage 없음
- bid/ask spread 없음
- 부분 체결 없음
- 장중 유동성 제약 약함
- 주문 실패나 가격 갭 리스크 미반영
- corporate action 처리 없음

교육용/연구용으로는 출발점이 될 수 있지만, 상업적으로 "투자 성과"를 말하기에는 부족하다.

### 4.4 데이터 소스 리스크가 크다

현재 가격 데이터는 `yfinance` 기반이다. yfinance는 PyPI 설명에서 Yahoo와 공식 제휴가 아니며 연구/교육 목적이고, 실제 다운로드 데이터 사용 권리는 Yahoo 약관을 확인해야 한다고 안내한다. 상업 서비스의 핵심 가격 데이터로 쓰기에는 법적/운영 리스크가 있다.

뉴스도 Marketaux, Naver, Alpha Vantage를 섞지만 현재 shared news는 글로벌 feed 중심이라 KR/US 시장별 relevance가 충분히 보장되지 않는다.

상업화 전 필요한 조치:

- 공식/상업용 가격 데이터 공급자 검토
- 데이터 라이선스 문서화
- 각 뉴스 아이템의 종목 연결 품질 평가
- 뉴스 deduplication과 source weighting 검증
- 데이터 결측/지연/오류를 성과 기록에 함께 저장

### 4.5 LLM 출력 안정성 보강이 필요하다

현재 `src/app/llm/openrouter.py`는 모델 응답에서 `{...}` 구간을 찾아 JSON으로 파싱한 뒤 Pydantic으로 검증한다. 하지만 OpenRouter는 이미 지원 모델에 대해 `response_format: json_schema` 기반 structured outputs를 제공한다. 무료/실험 모델은 지원 편차가 있을 수 있으므로, 모델별 지원 파라미터 확인과 fallback 전략이 필요하다.

권장 구조:

- structured output 지원 모델은 strict JSON Schema 사용
- 미지원 모델은 현재 방식 + repair/retry + 실패 원인 분류
- schema violation rate를 모델 평가 지표로 추가
- "투자 수익률"과 "운영 가능성"을 분리해서 랭킹

### 4.6 보안/비밀정보 관리가 위험하다

로컬 DB의 runtime/admin setting에는 provider 에러 메시지가 저장되며, 외부 API URL과 토큰이 에러 문자열에 포함될 가능성이 있다. 실제 검토 중에도 민감정보가 포함된 provider 에러 형태를 확인했다. 이 문서에는 값을 남기지 않는다.

필요한 조치:

- 즉시 노출 가능성이 있는 provider key 회전
- 에러 메시지 저장 전 query parameter/token 마스킹
- `runtime_secrets` DB 저장 시 암호화 또는 최소한 OS-level secret store 사용
- admin secrets 화면에서 full reveal 제한
- 공개 API와 admin API의 CORS 분리
- 운영 DB 백업/덤프 취급 정책 작성

### 4.7 규제/마케팅 리스크가 있다

현재 copy-trade endpoint와 공개 랭킹은 외부 사용자가 실제 투자를 따라 할 수 있는 형태로 보일 수 있다. "벤치마크/시뮬레이션"이라는 문구가 있어도, 수익률을 전면에 내세우면 투자 조언 또는 성과 광고로 오해될 여지가 있다.

SEC는 AI를 이용한 투자 관련 표시가 허위 또는 과장될 경우 문제 삼고 있으며, predictive data analytics 관련 규제 논의도 계속 이어져 왔다. 2025년에는 해당 PDA 제안 규칙들이 철회되었지만, AI-washing과 투자자 오인 리스크는 여전히 상업화의 핵심 위험이다.

상업화 전 최소 조건:

- 투자 조언 아님을 명확히 고지
- 실거래 아님, 지연 데이터 가능성, 체결 가정 명시
- 수익률 표시 기준과 기간 명시
- 모델별 시작일/거래 수/실패율 함께 표기
- copy-trade API 명칭 재검토. 예: `portfolio-snapshot`이 더 안전함

### 4.8 연구 재현성이 부족하다

학문적 가치가 있으려면 제3자가 같은 조건에서 결과를 재현할 수 있어야 한다.

현재 부족한 것:

- Alembic 의존성은 있지만 migration 파일이 보이지 않음
- 테스트 디렉터리 없음
- 실험 run manifest 없음
- 모델 endpoint/version freeze 없음
- 프롬프트 버전과 코드 commit의 강한 연결 부족
- market/news dataset snapshot export 없음
- baseline 전략 부족
- 통계적 유의성 분석 없음

## 5. 실제 가치가 있을 방향

### 방향 A: 연구용 "LLM 금융 행동 벤치마크"

가장 학문적 가치가 크다. 단순히 누가 돈을 벌었는지가 아니라, LLM이 동일 정보 조건에서 어떤 행동 편향을 보이는지 측정한다.

핵심 질문:

- LLM은 momentum, mean reversion, risk-off 상황을 구분하는가?
- 모델 크기/계열/structured output 안정성이 매매 품질과 관련 있는가?
- 같은 뉴스와 가격 조건에서 모델 간 포지션 집중도가 얼마나 높아지는가?
- 모델이 서로 비슷한 포트폴리오를 만들면 시스템 리스크가 증가하는가?

필요한 산출물:

- 고정된 replay dataset
- baseline 전략: equal-weight, momentum, buy-and-hold, random, no-trade
- 모델별 decision trace
- schema failure/timeout/rate-limit 지표
- 논문형 리포트와 공개 데이터셋

이 방향은 FinBen 같은 금융 LLM 벤치마크 흐름과도 맞고, LLM agent market simulation 연구와도 연결된다.

### 방향 B: "LLM 투자 에이전트 운영성 평가" SaaS/API

상업적 가치가 더 현실적이다. 수익률을 파는 대신, 금융 도메인에서 LLM endpoint가 얼마나 안정적으로 의사결정 포맷을 지키는지 평가한다.

팔 수 있는 것:

- 모델별 JSON/schema 준수율
- 금융 프롬프트별 hallucination/invalid action 비율
- latency, timeout, 429, provider failover 성능
- 동일 입력 반복 시 decision stability
- 비용 대비 운영 가능성

고객:

- 핀테크 회사
- AI 투자 리서치 팀
- LLM gateway/observability 업체
- 모델 제공사

이 방향은 규제상 "투자 추천"보다 안전하고, 현재 코드의 LLM 로그/실패율/운영 이벤트 구조를 활용하기 좋다.

### 방향 C: 공개 리더보드 + 연구 데이터셋

공개 사이트는 유지하되, 핵심 가치를 "투자 따라 하기"가 아니라 "모델 행동 데이터"로 포지셔닝한다.

추가하면 좋은 기능:

- cohort별 리더보드
- 모델별 sample size badge
- "투자 성과" 탭과 "운영 안정성" 탭 분리
- 프롬프트/응답 익명화 export
- 월간 리포트 자동 생성
- 데이터셋 DOI 또는 Hugging Face dataset 배포

### 방향 D: 한국/미국 양시장 LLM 비교 벤치마크

KR/US를 동시에 다루는 점은 차별점이다. 많은 영어권 금융 LLM 벤치마크는 미국 시장과 영어 뉴스에 치우친다.

차별화 방향:

- 한국어 뉴스와 영어 뉴스가 모델 판단에 미치는 차이
- 국내 종목명/티커/섹터 이해도
- 환율과 지역 시장 시간대가 판단에 미치는 영향
- bilingual prompt vs English-only prompt 비교

이 방향은 학문적으로도 좋고, 한국 시장 대상 상업 리서치에도 연결된다.

### 방향 E: Agent market simulation으로 확장

현재는 각 모델이 실제 시장 가격을 보고 독립적으로 포트폴리오를 조정한다. 다음 단계는 LLM agent들이 같은 시장 안에서 서로의 주문으로 가격을 움직이는 시뮬레이션이다.

필요한 확장:

- order book
- market/limit order
- partial fill
- liquidity provider 역할
- market maker/long-only/value/momentum agent prompt
- shock event 시나리오

이는 "LLM이 실제 시장을 이길 수 있는가"보다 더 좋은 연구 질문인 "LLM agent들이 시장 안정성에 어떤 영향을 주는가"를 다룰 수 있다.

## 6. 추천 우선순위

### 즉시: 1~2주

- provider token/key 회전 및 에러 메시지 마스킹
- 공개 화면과 API 문구에서 투자 조언/실거래 오해 제거
- `copy-trade` 명칭의 외부 노출 재검토
- 모델별 실패율과 마지막 성공 시각을 랭킹에 함께 표시
- composite score가 0인 상태를 숨기거나 "not implemented"로 표시
- 테스트 최소 세트 추가: trading engine, JSON parsing, ranking calculation

### 단기: 1개월

- 성과 지표 구현: daily return, volatility, Sharpe/Sortino, drawdown, turnover
- baseline 전략 추가
- cohort 리더보드 추가
- structured outputs 지원 모델에 `response_format` 적용
- model endpoint capability를 DB에 저장
- run manifest 생성: code commit, config, prompt version, model id, data window

### 중기: 2~3개월

- yfinance 의존을 provider abstraction 뒤로 완전히 숨기고 공식 데이터 공급자 검토
- 연구용 replay mode 구축
- dataset export 파이프라인 구축
- prompt variant 실험 설계
- 모델별 행동 분석 리포트 자동화
- 공개 API 문서와 데이터 사전 작성

### 장기: 3~6개월

- 논문/whitepaper 작성
- Hugging Face 또는 별도 dataset release
- 운영성 평가 API 상품화
- 한국/미국 bilingual financial agent benchmark로 포지셔닝
- order-book 기반 agent market simulation 연구 확장

## 7. 하지 말아야 할 방향

- 현재 수익률만 보고 "AI가 시장을 이긴다"는 식의 마케팅을 하지 말 것.
- yfinance 기반 데이터를 상업용 실시간 투자 데이터처럼 포장하지 말 것.
- 짧고 불균등한 운용 기간의 raw return을 모델 우열로 단정하지 말 것.
- 무료/실험 모델 endpoint를 장기적으로 동일한 모델이라고 가정하지 말 것.
- copy-trade API를 실제 매매 신호 서비스처럼 홍보하지 말 것.
- 규제 검토 없이 유료 투자 추천/구독 모델로 바로 전환하지 말 것.

## 8. 결론

이 프로젝트의 가장 좋은 방향은 "AI가 주식을 골라준다"가 아니다. 그 방향은 데이터 라이선스, 투자자 보호, 성과 광고, 체결 현실성 문제 때문에 위험하고 경쟁도 치열하다.

더 가치 있는 방향은 **LLM 금융 에이전트의 행동, 안정성, 실패 양상, 시장 조건별 의사결정을 장기적으로 관찰하는 벤치마크**다. 이미 필요한 뼈대는 있다. 다음 단계는 수익률 랭킹을 키우는 것이 아니라, 실험 설계와 데이터 신뢰성을 강화해서 연구자와 핀테크 팀이 믿고 쓸 수 있는 데이터와 API로 만드는 것이다.

## 9. 참고한 외부 자료

- OpenRouter structured outputs 문서: https://openrouter.ai/docs/guides/features/structured-outputs
- OpenRouter models API 문서: https://openrouter.ai/docs/guides/overview/models
- yfinance PyPI 설명 및 법적 고지: https://pypi.org/project/yfinance/
- SEC predictive data analytics rulemaking page: https://www.sec.gov/rules-regulations/2025/06/s7-12-23
- SEC AI-washing enforcement release, 2024-03-18: https://www.sec.gov/newsroom/press-releases/2024-36
- FinBen: A Holistic Financial Benchmark for Large Language Models: https://arxiv.org/abs/2402.12659
- Can Large Language Models Trade? Testing Financial Theories with LLM Agents in Market Simulations: https://arxiv.org/abs/2504.10789
