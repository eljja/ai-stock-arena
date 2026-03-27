# Step 2: 로컬 개발과 GitHub 연결

## 권장 흐름

1. 로컬에서 코드 작성
2. 로컬에서 최소 실행 확인
3. GitHub에 저장소 생성
4. Oracle 서버에서 clone
5. Oracle에서 운영용 `.env`와 PostgreSQL 설정
6. systemd로 상시 실행

## 현재 로컬 상태

- 프로젝트명: `AI Stock Arena`
- 로컬 Git 저장소: 초기화 완료
- 기본 프로젝트 골격: 생성 완료

## GitHub 저장소 권장값

- 저장소명: `ai-stock-arena`
- 가시성: private 권장
- 기본 브랜치: `main`

## GitHub 저장소 생성 후 로컬에서 실행할 명령

```powershell
git remote add origin https://github.com/<YOUR_GITHUB_ID>/ai-stock-arena.git
git add .
git commit -m "Initialize AI Stock Arena bootstrap"
git push -u origin main
```

## Oracle 서버 배포 기본 흐름

```bash
git clone https://github.com/<YOUR_GITHUB_ID>/ai-stock-arena.git
cd ai-stock-arena
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

이후 `.env`를 운영값으로 바꾸고 PostgreSQL을 연결한다.
