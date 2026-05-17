#!/usr/bin/env python3
"""
Garmin 수면 데이터 자동 분석 & 이메일 리포트
GitHub Actions cron으로 매일 실행 → 전날 수면 데이터 수집 → Gemini 분석 → 이메일 발송
"""

import os
import logging
import httpx
from datetime import date
from dotenv import load_dotenv
from garminconnect import Garmin
from google import genai

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

GARMIN_EMAIL    = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")
GEMINI_KEY      = os.getenv("GEMINI_API_KEY")
RESEND_API_KEY  = os.getenv("RESEND_API_KEY")
REPORT_TO       = os.getenv("REPORT_TO")


def fetch_sleep_data(target_date: str) -> dict:
    log.info(f"Garmin 로그인 중... (대상 날짜: {target_date})")
    client = Garmin(
        GARMIN_EMAIL,
        GARMIN_PASSWORD,
        prompt_mfa=lambda: input("Garmin MFA 코드: "),
    )
    client.login(os.path.expanduser("~/.garminconnect"))

    raw = client.get_sleep_data(target_date)
    dto = raw.get("dailySleepDTO", {})

    def min_to_hm(minutes):
        if minutes is None:
            return "N/A"
        h, m = divmod(int(minutes), 60)
        return f"{h}시간 {m}분"

    sleep_info = {
        "date":                 target_date,
        "sleep_start":          dto.get("sleepStartTimestampLocal"),
        "sleep_end":            dto.get("sleepEndTimestampLocal"),
        "total_sleep_minutes":  dto.get("sleepTimeSeconds", 0) // 60,
        "total_sleep_display":  min_to_hm(dto.get("sleepTimeSeconds", 0) // 60),
        "deep_sleep_minutes":   dto.get("deepSleepSeconds", 0) // 60,
        "deep_sleep_display":   min_to_hm(dto.get("deepSleepSeconds", 0) // 60),
        "light_sleep_minutes":  dto.get("lightSleepSeconds", 0) // 60,
        "light_sleep_display":  min_to_hm(dto.get("lightSleepSeconds", 0) // 60),
        "rem_sleep_minutes":    dto.get("remSleepSeconds", 0) // 60,
        "rem_sleep_display":    min_to_hm(dto.get("remSleepSeconds", 0) // 60),
        "awake_minutes":        dto.get("awakeSleepSeconds", 0) // 60,
        "awake_display":        min_to_hm(dto.get("awakeSleepSeconds", 0) // 60),
        "sleep_score":          dto.get("sleepScores", {}).get("overall", {}).get("value"),
        "avg_spo2":             dto.get("averageSpO2Value"),
        "avg_hrv":              dto.get("avgSleepHRV"),
        "avg_respiration":      dto.get("averageRespirationValue"),
        "restless_moments":     dto.get("restlessMomentsCount"),
        "sleep_need_minutes":   _safe_seconds(dto.get("sleepNeed")) // 60,
        "sleep_debt_minutes":   _safe_seconds(dto.get("sleepDebt")) // 60,
    }

    log.info(f"수면 데이터 수집 완료: {sleep_info['total_sleep_display']}, 점수={sleep_info['sleep_score']}")
    return sleep_info


def _safe_seconds(val) -> int:
    if val is None:
        return 0
    if isinstance(val, dict):
        return int(val.get("value", 0))
    return int(val)

def _pct(part, total):
    if not total:
        return 0
    return round(part / total * 100)


def analyze_with_gemini(sleep_info: dict) -> str:
    log.info("Gemini 분석 중...")
    client = genai.Client(api_key=GEMINI_KEY)

    prompt = f"""다음은 {sleep_info['date']} 수면 데이터입니다. 분석 리포트를 작성해주세요.

당신은 스포츠 의학과 수면 과학에 밝은 러닝 코치이자 건강 분석가입니다.
분석은 한국어로, 친근하지만 전문적인 톤으로 작성하세요.
불필요한 인사말이나 결론 요약은 생략하고 핵심 인사이트를 바로 전달하세요.

[수면 데이터]
- 총 수면시간: {sleep_info['total_sleep_display']} ({sleep_info['total_sleep_minutes']}분)
- 깊은 수면: {sleep_info['deep_sleep_display']} (전체의 {_pct(sleep_info['deep_sleep_minutes'], sleep_info['total_sleep_minutes'])}%)
- 얕은 수면: {sleep_info['light_sleep_display']} (전체의 {_pct(sleep_info['light_sleep_minutes'], sleep_info['total_sleep_minutes'])}%)
- REM 수면: {sleep_info['rem_sleep_display']} (전체의 {_pct(sleep_info['rem_sleep_minutes'], sleep_info['total_sleep_minutes'])}%)
- 각성 시간: {sleep_info['awake_display']}
- 수면 점수: {sleep_info['sleep_score'] or 'N/A'} / 100
- 평균 SpO2: {sleep_info['avg_spo2'] or 'N/A'}%
- 평균 HRV: {sleep_info['avg_hrv'] or 'N/A'}ms
- 평균 호흡수: {sleep_info['avg_respiration'] or 'N/A'} 회/분
- 뒤척임 횟수: {sleep_info['restless_moments'] or 'N/A'}회
- Garmin 권장 수면: {sleep_info.get('sleep_need_minutes', 0)}분 / 수면 부채: {sleep_info.get('sleep_debt_minutes', 0)}분

다음 형식으로 리포트를 작성해주세요:

## 📊 오늘의 수면 요약
(한 줄로 전반적인 수면 상태 평가)

## 🔍 단계별 분석
(깊은수면/REM/얕은수면 각각의 의미와 평가, 마라톤 회복 관점에서)

## ⚠️ 주목할 지표
(SpO2, HRV, 호흡수 중 이상 징후가 있으면 설명, 정상이면 긍정적으로)

## 💡 오늘의 권장 행동
(내일 훈련 강도 제안, 피로 관리 팁 등 구체적인 3가지)
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    log.info("Gemini 분석 완료")
    return response.text


def send_email(subject: str, body_md: str, sleep_info: dict):
    log.info(f"이메일 발송 중 → {REPORT_TO}")
    html_body = _md_to_html(body_md, sleep_info)

    response = httpx.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type":  "application/json",
        },
        json={
            "from":    "Garmin Reporter <onboarding@resend.dev>",
            "to":      [REPORT_TO],
            "subject": subject,
            "html":    html_body,
            "text":    body_md,
        },
        timeout=30,
    )

    if response.status_code in (200, 201):
        log.info("이메일 발송 완료!")
    else:
        raise Exception(f"Resend 발송 실패: {response.status_code} {response.text}")


def _md_to_html(text: str, sleep_info: dict) -> str:
    lines = []
    for line in text.split("\n"):
        if line.startswith("## "):
            lines.append(f"<h2 style='color:#333;border-bottom:2px solid #eee;padding-bottom:6px'>{line[3:]}</h2>")
        elif line.startswith("- ") or line.startswith("* "):
            lines.append(f"<li style='margin:4px 0'>{line[2:]}</li>")
        elif line.strip() == "":
            lines.append("<br>")
        else:
            lines.append(f"<p style='margin:6px 0'>{line}</p>")

    content = "\n".join(lines)
    score = sleep_info.get("sleep_score") or 0
    score_color = "#4CAF50" if score >= 80 else "#FF9800" if score >= 60 else "#F44336"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Apple SD Gothic Neo',sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
  <div style="background:linear-gradient(135deg,#1a237e,#283593);color:white;padding:20px;border-radius:12px;margin-bottom:20px">
    <h1 style="margin:0;font-size:22px">🌙 수면 분석 리포트</h1>
    <p style="margin:6px 0 0;opacity:0.85">{sleep_info['date']}</p>
  </div>
  <div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap">
    <div style="flex:1;min-width:120px;background:#f5f5f5;padding:14px;border-radius:10px;text-align:center">
      <div style="font-size:28px;font-weight:bold;color:{score_color}">{score or '—'}</div>
      <div style="font-size:12px;color:#666">수면 점수</div>
    </div>
    <div style="flex:1;min-width:120px;background:#f5f5f5;padding:14px;border-radius:10px;text-align:center">
      <div style="font-size:22px;font-weight:bold;color:#1976D2">{sleep_info['total_sleep_display']}</div>
      <div style="font-size:12px;color:#666">총 수면</div>
    </div>
    <div style="flex:1;min-width:120px;background:#f5f5f5;padding:14px;border-radius:10px;text-align:center">
      <div style="font-size:22px;font-weight:bold;color:#7B1FA2">{sleep_info['rem_sleep_display']}</div>
      <div style="font-size:12px;color:#666">REM 수면</div>
    </div>
    <div style="flex:1;min-width:120px;background:#f5f5f5;padding:14px;border-radius:10px;text-align:center">
      <div style="font-size:22px;font-weight:bold;color:#00796B">{sleep_info['deep_sleep_display']}</div>
      <div style="font-size:12px;color:#666">깊은 수면</div>
    </div>
  </div>
  <div style="background:white;border:1px solid #eee;border-radius:10px;padding:20px">
    {content}
  </div>
  <p style="font-size:11px;color:#aaa;text-align:center;margin-top:16px">
    Garmin Connect + Gemini AI 자동 분석 리포트
  </p>
</body>
</html>"""


def main():
    target_date = date.today().isoformat()
    log.info(f"=== 수면 리포트 시작: {target_date} ===")

    sleep_info  = fetch_sleep_data(target_date)
    report_text = analyze_with_gemini(sleep_info)

    score_str = f" (점수 {sleep_info['sleep_score']})" if sleep_info["sleep_score"] else ""
    subject   = f"🌙 수면 리포트 {target_date} — {sleep_info['total_sleep_display']}{score_str}"
    send_email(subject, report_text, sleep_info)

    log.info("=== 완료 ===")


if __name__ == "__main__":
    main()
