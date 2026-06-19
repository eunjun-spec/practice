import os
import json
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

init_db()


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
    return jsonify(kakao_text("장소를 계속 입력해주세요."))


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

    search_query = f"{area} 여행 후기"
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://search.naver.com/search.naver?ssc=tab.blog.all&query={encoded_query}"
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 🔍 네이버 블로그 제목을 잡기 위해 최신 클래스명(api_txt_lines) 추가
        review_elements = soup.select("a.api_txt_lines")
        
        # 만약 api_txt_lines로 못 잡으면 기존 title_link로 재시도
        if not review_elements:
            review_elements = soup.select("a.title_link")

        reviews = []
        for element in review_elements[:2]:  # 상위 2개만
            title = element.get_text(strip=True)
            if title:
                reviews.append(title)

        if reviews:
            review_list = [f"{i+1}. {t}" for i, t in enumerate(reviews)]
            result = f"✈️ [{area}] 최신 여행 후기 검색 결과입니다:\n\n" + "\n\n".join(review_list)
        else:
            result = f"[{area}]에 대한 최신 여행 후기를 찾지 못했습니다. (구조 변경 가능성)"

    except Exception as e:
        result = f"여행 후기 크롤링 중 오류 발생: {str(e)}"

    return jsonify(kakao_text(result))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
