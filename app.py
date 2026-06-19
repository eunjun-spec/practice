import os
import json
import sqlite3  # 찜 목록 DB를 위해 추가
import urllib.parse
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

# 1. Anthropic 대신 OpenAI 클라이언트 임포트
from openai import OpenAI

from db import (
    clear_state,
    delete_latest,
    get_schedules,
    get_state,
    init_db,
    save_schedule,
    save_state,
)

app = Flask(__name__)

# 💡 Render 환경 변수에서 OpenAI 키를 가져옵니다. 
# 만약 기존에 설정한 ANTHROPIC_API_KEY라는 이름을 그대로 쓰고 계셔도 작동하도록 fallback을 두었습니다.
api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
client = OpenAI(api_key=api_key)

# ==========================================
# ⭐️ [찜 기능] 내부 DB 로직 (app.py에 통합)
# ==========================================
WISH_DB = "wishlist.db"

def init_wish_db():
    """찜 목록 테이블 초기화"""
    conn = sqlite3.connect(WISH_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_wish(user_id, content):
    """찜한 내용 저장"""
    conn = sqlite3.connect(WISH_DB)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO wishlist (user_id, content) VALUES (?, ?)",
        (user_id, content)
    )
    conn.commit()
    conn.close()

def get_wishlist(user_id):
    """사용자의 찜 목록 가져오기"""
    conn = sqlite3.connect(WISH_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT content FROM wishlist WHERE user_id = ? ORDER BY id DESC",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [row["content"] for row in rows]
# ==========================================

# 서비스 시작 시 데이터베이스 파일들 초기화
init_db()
init_wish_db()


def kakao_text(text):
    """카카오톡 SimpleText 포맷에 맞춰 응답을 변환 (최대 950자 제한)"""
    safe_text = text[:950] + "..." if len(text) > 950 else text
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": safe_text
                    }
                }
            ]
        }
    }


@app.route("/", methods=["GET"])
def home():
    return "Server is running."


@app.route("/key-test", methods=["GET", "POST"])
def key_test():
    # API 키 검증 로직 (확인용)
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return jsonify(kakao_text("KEY 없음"))
    return jsonify(kakao_text(f"KEY 존재: {key[:15]}"))


@app.route("/travel", methods=["POST"])
def travel():
    data = request.get_json(silent=True) or {}
    
    country = data.get("action", {}).get("params", {}).get("country", "")
    feeling = data.get("action", {}).get("params", {}).get("feeling", "").strip()
    
    if not feeling:
        feeling = data.get("userRequest", {}).get("utterance", "").strip()

    area = "국내" if country == "in" else "해외"

    system_prompt = "당신은 여행 전문가입니다."
    user_prompt = f"""사용자가 {area} 여행을 원합니다.

원하는 여행 스타일:
{feeling}

실존하는 여행지 1곳 추천

형식:

1. 여행지명


다른 설명 없이 출력"""

    try:
        # 💡 OpenAI GPT-4o-mini 모델로 호출 문법 변경
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=500,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 답변 텍스트 추출 방식 변경
        ai_text = response.choices[0].message.content.strip()
        return jsonify(kakao_text(ai_text))
        
    except Exception as e:
        return jsonify(kakao_text(f"OpenAI API 에러 발생: {str(e)}"))


@app.route("/schedule_create", methods=["POST"])
def schedule_create():
    data = request.get_json(silent=True) or {}
    user_id = data.get("userRequest", {}).get("user", {}).get("id", "guest")

    save_state(user_id, "place", {"start": "", "end": "", "places": []})
    return jsonify(kakao_text("여행 날짜를 입력해주세요."))


@app.route("/schedule_date", methods=["POST"])
def schedule_date():
    data = request.get_json(silent=True) or {}
    
    try:
        user_id = data["userRequest"]["user"]["id"]
        date = data.get("action", {}).get("params", {}).get("date", "")
        start, end = date.split("~")
    except Exception:
        return jsonify(kakao_text("예: 2026-08-01~2026-08-03"))

    save_state(user_id, "place", {
        "start": start.strip(),
        "end": end.strip(),
        "places": []
    })
    return jsonify(kakao_text("계속하시려면 장소 버튼을 누르거나 장소를 입력해주세요"))


@app.route("/schedule_place", methods=["POST"])
def schedule_place():
    data = request.get_json(silent=True) or {}
    
    try:
        user_id = data["userRequest"]["user"]["id"]
        place = data.get("action", {}).get("params", {}).get("place", "")
    except KeyError:
        return jsonify(kakao_text("잘못된 요청입니다."))

    state = get_state(user_id)
    if not state:
        return jsonify(kakao_text("먼저 일정 생성"))

    temp = state["temp"]
    temp["places"].append(place)
    save_state(user_id, "place", temp)

    result = [f"{i}. {p}" for i, p in enumerate(temp["places"], 1)]
    return jsonify(kakao_text("\n".join(result)))


@app.route("/schedule_order", methods=["POST"])
def schedule_order():
    data = request.get_json(silent=True) or {}
    
    try:
        user_id = data["userRequest"]["user"]["id"]
        params = data.get("action", {}).get("params", {})
        a = int(params["from"])
        b = int(params["to"])
    except Exception:
        return jsonify(kakao_text("번호 오류"))

    state = get_state(user_id)
    temp = state["temp"]
    places = temp["places"]

    places[a - 1], places[b - 1] = places[b - 1], places[a - 1]
    save_state(user_id, "place", temp)

    return jsonify(kakao_text("순서 변경 완료"))


@app.route("/schedule_save", methods=["POST"])
def schedule_save():
    data = request.get_json(silent=True) or {}
    
    try:
        user_id = data["userRequest"]["user"]["id"]
    except KeyError:
        return jsonify(kakao_text("잘못된 요청입니다."))

    state = get_state(user_id)
    if not state:
        return jsonify(kakao_text("저장할 일정 없음"))

    temp = state["temp"]
    save_schedule(user_id, temp["start"], temp["end"], temp["places"])
    clear_state(user_id)

    return jsonify(kakao_text("저장 완료"))


@app.route("/schedule_view", methods=["POST"])
def schedule_view():
    data = request.get_json(silent=True) or {}
    
    try:
        user_id = data["userRequest"]["user"]["id"]
    except KeyError:
        return jsonify(kakao_text("잘못된 요청입니다."))

    rows = get_schedules(user_id)
    if not rows:
        return jsonify(kakao_text("일정 없음"))

    result = []
    for r in rows:
        places = json.loads(r["places"])
        places_str = " / ".join(places)
        result.append(f"{r['start_date']}\n~\n{r['end_date']}\n\n{places_str}")

    return jsonify(kakao_text("\n\n".join(result)))


@app.route("/schedule_delete", methods=["POST"])
def schedule_delete():
    data = request.get_json(silent=True) or {}
    
    try:
        user_id = data["userRequest"]["user"]["id"]
    except KeyError:
        return jsonify(kakao_text("잘못된 요청입니다."))

    delete_latest(user_id)
    return jsonify(kakao_text("최근 일정 삭제 완료"))

@app.route("/travel_review", methods=["POST"])
def travel_review():
    data = request.get_json(silent=True) or {}
    area = data.get("action", {}).get("params", {}).get("area", "").strip()

    if not area:
        return jsonify(kakao_text("여행지 정보가 올바르게 전달되지 않았습니다."))

    # 구글에서 '여행지 + 여행 후기'로 검색
    search_query = f"{area} 여행 후기"
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://www.google.com/search?q={encoded_query}&hl=ko"
    
    # 구글 크롤링을 위해 일반 PC 브라우저처럼 보이도록 헤더 설정
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        # 카카오톡 3초 제한을 위해 타임아웃 설정
        r = requests.get(url, headers=headers, timeout=2.5)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 구글 검색 결과의 각 사이트 설명(미리보기 텍스트)을 담고 있는 최신 클래스명들입니다.
        # 구글은 보통 'VwiC3b' 혹은 'YrbPfc' 클래스를 사용합니다.
        review_elements = soup.select(".VwiC3b, .YrbPfc")

        if review_elements:
            # 검색 결과 중 가장 내용이 알찬 첫 번째 혹은 두 번째 리뷰 내용을 가져옵니다.
            description = ""
            for el in review_elements[:2]:
                text = el.get_text(strip=True)
                if len(text) > 30:  # 너무 짧은 텍스트는 패스
                    description = text
                    break
            
            if not description:
                description = review_elements[0].get_text(strip=True)

            result = f"✍️ [{area}] 실제 웹 리뷰 요약입니다:\n\n{description}"
        else:
            result = f"[{area}]에 대한 실제 리뷰를 구글에서 찾지 못했습니다."

    except requests.exceptions.Timeout:
        result = "⏱️ 리뷰를 읽어오는 중 시간 초과가 발생했습니다. 다시 시도해주세요."
    except Exception as e:
        result = f"리뷰 크롤링 중 오류 발생: {str(e)}"

    return jsonify(kakao_text(result))


@app.route("/wish_add", methods=["POST"])
def wish_add():
    data = request.get_json(silent=True) or {}
    
    try:
        user_id = data["userRequest"]["user"]["id"]
        content = data.get("action", {}).get("params", {}).get("content", "").strip()
    except KeyError:
        return jsonify(kakao_text("잘못된 요청입니다."))

    if not content:
        content = data.get("userRequest", {}).get("utterance", "").strip()

    if not content:
        return jsonify(kakao_text("찜할 내용을 찾을 수 없습니다."))

    save_wish(user_id, content)
    return jsonify(kakao_text(f"❤️ '{content}' 찜 목록에 저장 완료!"))


@app.route("/wish_view", methods=["POST"])
def wish_view():
    data = request.get_json(silent=True) or {}
    
    try:
        user_id = data["userRequest"]["user"]["id"]
    except KeyError:
        return jsonify(kakao_text("잘못된 요청입니다."))

    wishes = get_wishlist(user_id)
    if not wishes:
        return jsonify(kakao_text("아직 찜한 내역이 없습니다."))

    result = [f"{i}. {w}" for i, w in enumerate(wishes, 1)]
    response_text = "⭐️ 나의 찜 목록 ⭐️\n\n" + "\n".join(result)
    return jsonify(kakao_text(response_text))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
