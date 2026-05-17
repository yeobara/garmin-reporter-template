#!/usr/bin/env python3
"""
Garmin 러닝 데이터 분석 & 이메일 리포트
GitHub Actions workflow_dispatch로 수동 실행 → 오늘 마지막 러닝 분석 → 이메일 발송
"""

import os
import logging
import httpx
from datetime import date

from google import genai
from dotenv import load_dotenv
from garminconnect import Garmin

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

GARMIN_EMAIL    = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")
GEMINI_KEY      = os.getenv("GEMINI_API_KEY")
RESEND_API_KEY  = os.getenv("RESEND_API_KEY")
REPORT_TO       = os.getenv("REPORT_TO")


def m_to_pace(meters_per_sec) -> str:
    if not meters_per_sec or meters_per_sec == 0:
        return "N/A"
    sec_per_km = 1000 / meters_per_sec
    m, s = divmod(int(sec_per_km), 60)
    return f"{m}'{s:02d}\""

def sec_to_hms(seconds) -> str:
    if not seconds:
        return "N/A"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}시간 {m}분 {s}초"
    return f"{m}분 {s}초"

def meters_to_km(meters) -> str:
    if not meters:
        return "N/A"
    return f"{meters / 1000:.2f}km"

def safe(val, unit="", decimals=1) -> str:
    if val is None:
        return "N/A"
    if decimals == 0:
        return f"{int(val)}{unit}"
    return f"{round(val, decimals)}{unit}"


def fetch_last_run() -> dict:
    log.info("Garmin Connect 연결 중...")
    client = Garmin(
        GARMIN_EMAIL,
        GARMIN_PASSWORD,
        prompt_mfa=lambda: input("Garmin MFA 코드: "),
    )
    client.login(os.path.expanduser("~/.garminconnect"))
    log.info("로그인 성공")

    today = date.today().isoformat()
    log.info(f"오늘({today}) 러닝 데이터 조회 중...")

    activities  = client.get_activities(0, 20)
    today_runs  = [
        a for a in activities
        if a.get("startTimeLocal", "").startswith(today)
        and "running" in a.get("activityType", {}).get("typeKey", "").lower()
    ]

    if not today_runs:
        log.warning("오늘 러닝 데이터가 없어요.")
        return {}

    last        = today_runs[0]
    activity_id = last.get("activityId")
    log.info(f"오늘 러닝 {len(today_runs)}개 발견 → 마지막 러닝 분석")

    details = client.get_activity(activity_id)
    splits  = client.get_activity_splits(activity_id)

    laps = []
    for i, lap in enumerate(splits.get("lapDTOs", []), 1):
        laps.append({
            "lap":      i,
            "distance": meters_to_km(lap.get("distance")),
            "pace":     m_to_pace(lap.get("averageSpeed")),
            "hr":       safe(lap.get("averageHR"), "bpm", 0),
            "cadence":  safe(lap.get("averageRunCadence"), "spm", 0),
        })

    run_info = {
        "date":                 today,
        "name":                 last.get("activityName", "러닝"),
        "distance":             meters_to_km(last.get("distance")),
        "duration":             sec_to_hms(last.get("duration")),
        "avg_pace":             m_to_pace(last.get("averageSpeed")),
        "best_pace":            m_to_pace(last.get("maxSpeed")),
        "avg_hr":               safe(last.get("averageHR"), "bpm", 0),
        "max_hr":               safe(last.get("maxHR"), "bpm", 0),
        "avg_cadence":          safe(last.get("averageRunningCadenceInStepsPerMinute"), "spm", 0),
        "elevation_gain":       safe(last.get("elevationGain"), "m", 0),
        "calories":             safe(last.get("calories"), "kcal", 0),
        "aerobic_te":           safe(last.get("aerobicTrainingEffect")),
        "anaerobic_te":         safe(last.get("anaerobicTrainingEffect")),
        "training_load":        safe(last.get("activityTrainingLoad"), "", 0),
        "vo2max":               safe(last.get("vO2MaxValue")),
        "avg_power":            safe(last.get("avgPower"), "W", 0),
        "normalized_power":     safe(last.get("normPower"), "W", 0),
        "ground_contact":       safe(last.get("avgGroundContactTime"), "ms", 0),
        "vertical_oscillation": safe(last.get("avgVerticalOscillation"), "cm"),
        "stride_length":        safe(last.get("avgStrideLength"), "m"),
        "recovery_time":        last.get("recoveryTime"),
        "laps":                 laps,
        "total_runs_today":     len(today_runs),
    }

    log.info(f"데이터 수집 완료: {run_info['distance']} / 페이스 {run_info['avg_pace']}")
    return run_info


def analyze_with_gemini(run_info: dict) -> str:
    log.info("Gemini AI 분석 중...")
    client = genai.Client(api_key=GEMINI_KEY)

    laps_text = "\n".join([
        f"  - {l['lap']}km: 페이스 {l['pace']} | 심박 {l['hr']} | 케이던스 {l['cadence']}"
        for l in run_info["laps"]
    ]) if run_info["laps"] else "  랩 데이터 없음"

    recovery_text = f"{run_info['recovery_time']}시간" if run_info.get("recovery_time") else "N/A"

    prompt = f"""다음은 {run_info['date']} 러닝 데이터입니다. 전문적인 분석 리포트를 작성해주세요.

[기본 정보]
- 액티비티명: {run_info['name']}
- 거리: {run_info['distance']}
- 시간: {run_info['duration']}
- 평균 페이스: {run_info['avg_pace']}
- 최고 페이스: {run_info['best_pace']}

[심박수]
- 평균 심박: {run_info['avg_hr']}
- 최대 심박: {run_info['max_hr']}

[러닝 역학]
- 평균 케이던스: {run_info['avg_cadence']}
- 지면 접촉 시간: {run_info['ground_contact']}
- 수직 진동: {run_info['vertical_oscillation']}
- 스트라이드 길이: {run_info['stride_length']}

[파워]
- 평균 파워: {run_info['avg_power']}
- 정규화 파워: {run_info['normalized_power']}

[훈련 효과]
- 유산소 훈련 효과: {run_info['aerobic_te']} / 5.0
- 무산소 훈련 효과: {run_info['anaerobic_te']} / 5.0
- 훈련 부하: {run_info['training_load']}
- VO2max: {run_info['vo2max']}
- 권장 회복 시간: {recovery_text}

[기타]
- 고도 상승: {run_info['elevation_gain']}
- 칼로리: {run_info['calories']}

[랩별 페이스]
{laps_text}

다음 형식으로 리포트를 작성해주세요:

## 🏃 오늘의 러닝 요약
(전반적인 달리기 퀄리티 한 줄 평가)

## 📊 페이스 & 심박 분석
(페이스와 심박수의 관계, 랩별 페이스 변화 패턴 해석)

## ⚙️ 러닝 역학 분석
(케이던스, 지면 접촉 시간, 수직 진동, 스트라이드 등 생체역학 지표 해석)

## ⚡ 파워 & 훈련 효과
(파워 데이터와 훈련 효과 점수 해석, 오늘 달리기의 훈련 목적 분석)

## 💡 개선 포인트 & 다음 훈련 제안
(데이터 기반으로 개선할 점 2~3가지, 다음 훈련 권장)
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    log.info("AI 분석 완료")
    return response.text


def send_email(subject: str, body_md: str, run_info: dict):
    log.info(f"이메일 발송 중 → {REPORT_TO}")
    html_body = _md_to_html(body_md, run_info)

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


def _md_to_html(text: str, run_info: dict) -> str:
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

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Apple SD Gothic Neo',sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
  <div style="background:linear-gradient(135deg,#1b5e20,#2e7d32);color:white;padding:20px;border-radius:12px;margin-bottom:20px">
    <h1 style="margin:0;font-size:22px">🏃 러닝 분석 리포트</h1>
    <p style="margin:6px 0 0;opacity:0.85">{run_info['date']}</p>
  </div>
  <div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap">
    <div style="flex:1;min-width:110px;background:#f5f5f5;padding:14px;border-radius:10px;text-align:center">
      <div style="font-size:22px;font-weight:bold;color:#1976D2">{run_info['distance']}</div>
      <div style="font-size:12px;color:#666">거리</div>
    </div>
    <div style="flex:1;min-width:110px;background:#f5f5f5;padding:14px;border-radius:10px;text-align:center">
      <div style="font-size:22px;font-weight:bold;color:#2e7d32">{run_info['avg_pace']}</div>
      <div style="font-size:12px;color:#666">평균 페이스</div>
    </div>
    <div style="flex:1;min-width:110px;background:#f5f5f5;padding:14px;border-radius:10px;text-align:center">
      <div style="font-size:22px;font-weight:bold;color:#c62828">{run_info['avg_hr']}</div>
      <div style="font-size:12px;color:#666">평균 심박</div>
    </div>
    <div style="flex:1;min-width:110px;background:#f5f5f5;padding:14px;border-radius:10px;text-align:center">
      <div style="font-size:22px;font-weight:bold;color:#6a1b9a">{run_info['avg_cadence']}</div>
      <div style="font-size:12px;color:#666">케이던스</div>
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
    log.info("=== 러닝 리포트 시작 ===")

    run_info = fetch_last_run()

    if not run_info:
        log.info("오늘 러닝 데이터가 없어서 종료합니다.")
        return

    report_text = analyze_with_gemini(run_info)

    subject = f"🏃 러닝 리포트 {run_info['date']} — {run_info['distance']} / {run_info['avg_pace']}"
    send_email(subject, report_text, run_info)

    log.info("=== 완료 ===")


if __name__ == "__main__":
    main()
