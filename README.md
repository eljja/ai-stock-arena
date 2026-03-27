# AI Stock Arena

여러 LLM 모델의 주식 투자 의사결정 성능을 동일한 규칙으로 비교하는 프로젝트다.

현재 완료 범위:

- Step 1: 요구사항 확정
- Step 1: 시장 범위, 수수료 기본값, 점수 체계, 데이터 소스 정책 정리
- Step 1: 이후 구현에서 사용할 기본 설정 파일 초안 작성

프로젝트 핵심 목표:

- OpenRouter 모델별 독립 포트폴리오 운영
- 코스피, 코스닥, 미국 시장 가상 투자 자동화
- 1시간 단위 시장 감시와 매매 판단
- 거래 이력, 보유 종목, 성과 지표의 지속 저장
- 웹 대시보드로 모델별 성능 비교

프로젝트 이름:

- 서비스명: `AI Stock Arena`
- 저장소명 권장: `ai-stock-arena`

문서:

- [Step 1 명세서](D:\Codex\docs\step-01-system-spec.md)
- [기본 설정 예시](D:\Codex\config\defaults.example.toml)
- [환경 변수 예시](D:\Codex\.env.example)

다음 구현 단계:

1. PostgreSQL 스키마와 애플리케이션 설정 계층 구현
2. OpenRouter 모델 동기화와 포트폴리오 초기화 구현
3. 시장 스크리너, 시세 수집기, 거래 엔진 구현
4. FastAPI API와 Streamlit 대시보드 구현
5. Oracle Cloud 배포 및 systemd 서비스 구성
