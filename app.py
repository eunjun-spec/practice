from flask import Flask, request, jsonify
import random
import requests
from bs4 import BeautifulSoup
import urllib.parse
import os
from google import genai

app = Flask(__name__)


def kakao_text(text):
    return {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": text[:1000]
                }
            }]
        }
    }


@app.route("/", methods=["GET"])
def home():
    return "Server is running."


# 기존 테스트용
@app.route("/text", methods=["GET", "POST"])
def text_skill():
    return jsonify(kakao_text(str(random.randint(1, 10))))


@app.route("/image", methods=["GET", "POST"])
def image_skill():
    response = {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleImage": {
                    "imageUrl": "https://t1.daumcdn.net/friends/prod/category/M001_friends_ryan2.jpg",
                    "altText": "hello I'm Ryan"
                }
            }]
        }
    }
    return jsonify(response)


# 1. 데이터 그대로 주고받기
@app.route("/echo", methods=["POST"])
def echo_skill():
    data = request.get_json(silent=True) or {}
    user_input = data.get("userRequest", {}).get("utterance", "입력값이 없습니다.")
    return jsonify(kakao_text(user_input))


# 2. 울산 날씨 크롤링은 이전에 추가했던 버전 유지 가능
# 여기서는 생략


# 3. 시간/발화/파라미터 확인
@app.route("/params-check", methods=["POST"])
def params_check():
    data = request.get_json(silent=True) or {}

    user_request = data.get("userRequest", {})
    action = data.get("action", {})
    params = action.get("params", {})

    a = user_request.get("timezone", "timezone 없음")
    b = user_request.get("utterance", "utterance 없음")
    c = params.get("파라미터", "파라미터 없음")
    d = params.get("파라미터2", "파라미터2 없음")

    text = f"{a} / {b} / {c} / {d}"
    return jsonify(kakao_text(text))


# 4. 파라미터 활용 구글 기사 데이터 가져오기
@app.route("/google-news", methods=["POST"])
def google_news():
    data = request.get_json(silent=True) or {}
    y = data.get("action", {}).get("params", {}).get("파라미터", "").strip()

    if not y:
        return jsonify(kakao_text("파라미터 값이 없습니다."))

    query = urllib.parse.quote(y)
    url = f"https://www.google.com/search?q={query}&tbm=nws"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # Google 뉴스 검색 결과에서 자주 보이는 제목 선택자들 시도
        items = soup.select(".n0jPhd") or soup.select(".mCBkyc") or soup.select(".DKV0Md")

        titles = []
        for item in items[:5]:
            title = item.get_text(strip=True)
            if title:
                titles.append(title)

        if titles:
            result = y + " 검색 결과:\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(titles)])
        else:
            result = f"{y} 검색 결과를 찾지 못했습니다."

    except Exception as e:
        result = f"구글 뉴스 조회 중 오류: {str(e)}"

    return jsonify(kakao_text(result))


# 5. 파라미터로 Gemini 연동하기
@app.route("/gemini-param", methods=["POST"])
def gemini_param():
    data = request.get_json(silent=True) or {}
    tt = data.get("action", {}).get("params", {}).get("파라미터", "").strip()

    if not tt:
        return jsonify(kakao_text("파라미터 값이 없습니다."))

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return jsonify(kakao_text("GEMINI_API_KEY 환경변수가 설정되지 않았습니다."))

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=tt
        )
        result_text = response.text if response.text else "응답이 비어 있습니다."
    except Exception as e:
        result_text = f"Gemini 호출 중 오류: {str(e)}"

    return jsonify(kakao_text(result_text))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

