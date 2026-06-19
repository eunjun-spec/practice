import os
import json
import sqlite3  # 찜 목록 DB를 위해 추가
import urllib.parse
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
# 1. Gemini 대신 Anthropic 클라이언트 임포트
from anthropic import Anthropic

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
# 💡 Render의 환경 변수를 직접 읽어와서 Anthropic 클라이언트에 넘겨줍니다.
api_key = os.environ.get("ANTHROPIC_API_KEY")
client = Anthropic(api_key=api_key)

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
    # 3. API 키 검증 로직 변경
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return jsonify(kakao_text("KEY 없음"))
    return jsonify(kakao_text(f"KEY 존재: {key[:15]}"))


@app.route("/travel", methods=["POST"])
def travel():
    data = request.get_json(silent=True) or {}
    
    # 💡 카카오톡 챗봇 파라미터에서 country와 feeling을 각각 가져옵니다.
    country = data.get("action", {}).get("params", {}).get("country", "")
    feeling = data.get("action", {}).get("params", {}).get("feeling", "").strip()
    
    # 만약 feeling 파라미터가 비어있을 때를 대비한 방어 코드 (선택사항)
    if not feeling:
        feeling = data.get("userRequest", {}).get("utterance", "").strip()

    area = "국내" if country == "in" else "해외"

    system_prompt = "당신은 여행 전문가입니다."
    user_prompt = f"""사용자가 {area} 여행을 원합니다.

원하는 여행 스타일:
{feeling}

실존하는 여행지 2곳 추천

형식:

1. 여행지명

2. 여행지명

다른 설명 없이 출력"""

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        return jsonify(kakao_text(response.content[0].text))
    except Exception as e:
        return jsonify(kakao_text(str(e)))


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

    # 두 요소의 순서 바꿈
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

    # 1. 뷰티풀수프 크롤링을 위해 모바일 검색 URL로 변경 (더 가볍고 구조가 명확함)
    search_query = f"{area} 여행 후기"
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://m.search.naver.com/search.naver?where=m_blog&query={encoded_query}"
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
        )
    }

    try:
        # 카카오톡 3초 제한을 고려하여 타임아웃을 2.5초로 타이트하게 잡음
        r = requests.get(url, headers=headers, timeout=2.5)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 네이버 모바일 블로그 검색 결과의 본문 미리보기 클래스
        first_post = soup.select_one(".api_txt_lines.dsc_txt")

        if first_post:
            description = first_post.get_text(strip=True)
            result = f"✍️ [{area}] 최신 블로그 여행 후기 요약입니다:\n\n{description}"
        else:
            result = f"[{area}]에 대한 블로그 검색 결과를 찾지 못했습니다."

    except requests.exceptions.Timeout:
        result = "⏱️ 네이버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
    except Exception as e:
        result = f"여행 후기 크롤링 중 오류 발생: {str(e)}"

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
        # 만약 파라미터가 비어있다면 사용자가 입력한 전체 대화 내용을 가져옵니다.
        content = data.get("userRequest", {}).get("utterance", "").strip()

    if not content:
        return jsonify(kakao_text("찜할 내용을 찾을 수 없습니다."))

    # 내부 함수 호출하여 DB에 저장
    save_wish(user_id, content)
    
    return jsonify(kakao_text(f"❤️ '{content}' 찜 목록에 저장 완료!"))


@app.route("/wish_view", methods=["POST"])
def wish_view():
    data = request.get_json(silent=True) or {}
    
    try:
        user_id = data["userRequest"]["user"]["id"]
    except KeyError:
        return jsonify(kakao_text("잘못된 요청입니다."))

    # 내부 함수 호출하여 DB에서 해당 사용자의 찜 목록 읽어오기
    wishes = get_wishlist(user_id)
    
    if not wishes:
        return jsonify(kakao_text("아직 찜한 내역이 없습니다."))

    # 번호를 붙여서 리스트 형태로 포맷팅
    result = [f"{i}. {w}" for i, w in enumerate(wishes, 1)]
    
    response_text = "⭐️ 나의 찜 목록 ⭐️\n\n" + "\n".join(result)
    return jsonify(kakao_text(response_text))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
