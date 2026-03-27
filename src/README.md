# Source Layout

Step 2부터 아래 구조로 구현한다.

- `src/app/config/` 설정 로더와 환경 변수
- `src/app/db/` SQLAlchemy 모델과 세션
- `src/app/market_data/` 가격 공급자와 스크리닝
- `src/app/llm/` OpenRouter 연동
- `src/app/trading/` 가상 체결과 성과 계산
- `src/app/api/` FastAPI
- `src/app/dashboard/` Streamlit
- `src/app/jobs/` 스케줄러
- `src/app/cli/` 로컬 부트스트랩과 운영용 명령
