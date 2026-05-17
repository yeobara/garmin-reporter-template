# Garmin AI 리포트

가민 웨어러블 데이터를 AI가 분석해서 매일 이메일로 보내주는 자동화 도구입니다.
서버 없이 **GitHub Actions만으로** 동작합니다.

---

## 어떤 이메일이 오나요?

### 수면 리포트 — 매일 오전 9시 자동 발송
- 수면 점수, 총 수면시간, 깊은수면 / REM / 얕은수면 비율 분석
- HRV, SpO2, 호흡수 해석
- 오늘의 회복 상태와 훈련 강도 제안

### 러닝 리포트 — 달린 날 수동 실행
- 거리, 페이스, 심박수 / 랩별 페이스 변화 분석
- 케이던스, 지면 접촉 시간, 수직 진동 등 생체역학 지표
- AI 코칭 피드백과 다음 훈련 제안

---

## 준비물

| 항목 | 비용 | 발급 시간 |
|------|------|---------|
| 가민 기기 (수면 추적 지원 모델) | 기존 소유 | — |
| GitHub 계정 | 무료 | — |
| Gemini API 키 | 무료 | 2분 |
| Resend 계정 | 무료 (월 3,000건) | 5분 |

**총 설정 시간: 20~30분**

---

## 설정 방법

### 1단계 — 레포 Fork

이 페이지 우상단 **[Fork]** 버튼을 클릭해 내 GitHub 계정으로 복사합니다.

---

### 2단계 — API 키 발급

#### Gemini API 키 (AI 분석용)

1. [Google AI Studio](https://aistudio.google.com) 접속
2. 우상단 **[Get API key]** 클릭
3. **[Create API key]** → 키 복사 (`AIza...` 형태)

#### Resend API 키 (이메일 발송용)

1. [Resend](https://resend.com) 접속 → 회원가입
2. 좌측 메뉴 **[API Keys]** → **[Create API Key]**
3. 키 복사 (`re_...` 형태)

> **중요**: Resend 무료 플랜은 Resend 가입 이메일 주소로만 발송됩니다.
> `REPORT_TO`에는 Resend에 가입한 이메일을 입력하세요.

---

### 3단계 — GitHub Secrets 설정

Fork한 내 레포 → **Settings** → **Secrets and variables** → **Actions** → **[New repository secret]**

아래 5개를 하나씩 추가합니다.

| Secret 이름 | 입력할 값 |
|------------|---------|
| `GARMIN_EMAIL` | 가민 Connect 로그인 이메일 |
| `GARMIN_PASSWORD` | 가민 Connect 비밀번호 |
| `GEMINI_API_KEY` | 2단계에서 발급한 키 (`AIza...`) |
| `RESEND_API_KEY` | 2단계에서 발급한 키 (`re_...`) |
| `REPORT_TO` | 리포트 받을 이메일 (Resend 가입 이메일) |

---

### 4단계 — GitHub Actions 활성화

Fork한 레포 → **Actions** 탭 → **[I understand my workflows, enable them]** 클릭

완료! 다음 날 오전 9시에 첫 수면 리포트가 도착합니다.

---

## 러닝 리포트 실행 방법

달리고 나서 가민 앱에 데이터가 동기화되면:

**Actions** 탭 → **[러닝 리포트 (수동 실행)]** → **[Run workflow]** → **[Run workflow]**

약 30초 후 이메일이 도착합니다.

---

## 자주 묻는 질문

**Q. 가민 2단계 인증(MFA)을 사용 중인데 동작하나요?**

MFA를 비활성화해야 합니다.
가민 Connect 앱 → 프로필 → 계정 설정 → 보안 → 2단계 인증 해제

---

**Q. 이메일이 안 와요.**

1. Actions 탭에서 워크플로우 실행 기록을 확인하세요.
2. 빨간 X가 있다면 클릭해 로그를 확인하세요.
3. Resend 대시보드에서 발송 기록을 확인하세요.

가장 흔한 원인: `REPORT_TO`가 Resend에 가입한 이메일과 다른 경우.

---

**Q. 리포트 발송 시간을 바꾸고 싶어요.**

`.github/workflows/sleep_report.yml`의 cron 값을 수정하세요.

```
'0 0 * * *'   → UTC 00:00 (KST 09:00) ← 기본값
'0 22 * * *'  → UTC 22:00 (KST 07:00)
'0 1 * * *'   → UTC 01:00 (KST 10:00)
```

[crontab.guru](https://crontab.guru)에서 원하는 시간을 확인할 수 있습니다.

---

**Q. 수면 리포트만 / 러닝 리포트만 사용하고 싶어요.**

필요 없는 워크플로우 파일을 삭제하면 됩니다.
- 수면만: `.github/workflows/running_report.yml` 삭제
- 러닝만: `.github/workflows/sleep_report.yml` 삭제

---

**Q. AI 분석 내용을 커스터마이징하고 싶어요.**

`sleep_reporter.py` / `running_reporter.py` 안의 `prompt` 변수를 수정하세요.
원하는 분석 항목이나 톤을 자유롭게 바꿀 수 있습니다.

---

## 기술 스택

| 역할 | 도구 |
|------|------|
| 데이터 수집 | garminconnect (비공식 API) |
| AI 분석 | Google Gemini 2.5 Flash |
| 이메일 발송 | Resend |
| 자동 스케줄링 | GitHub Actions |

---

## 주의사항

- `garminconnect`는 비공식 라이브러리로, 가민이 API를 변경하면 작동하지 않을 수 있습니다.
- 개인 용도로만 사용하세요. 타인의 계정 정보를 수집하는 서비스로 운영하는 것은 가민 이용약관에 위반될 수 있습니다.
