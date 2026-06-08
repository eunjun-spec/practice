import os
import random
import requests
import urllib.parse
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

app = Flask(__name__)

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)


def kakao_text(text):
    """카카오톡 텍스트 응답 규격 생성 (1000자 제한 안전장치)"""
    # 만약의 상황을 대비해 950자에서 자르고 말줄임표를 추가합니다.
    safe_text = text[:950] + "..." if len(text) > 950 else text
    return {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": safe_text
                }
            }]
        }
    }

@app.route("/", methods=["GET"])
def home():
    return "Server is running."

@app.route("/key-test", methods=["GET", "POST"])
def key_test():

    key = os.getenv("GEMINI_API_KEY")

    if not key:
        return jsonify(kakao_text("KEY 없음"))

    return jsonify(
        kakao_text(
            f"KEY 존재: {key[:15]}"
        )
    )


@app.route("/travel", methods=["POST"])
def travel():

    data = request.get_json(silent=True) or {}

    country = data.get("action", {}).get("params", {}).get("country", "")

    feeling = data.get("userRequest", {}).get("utterance", "").strip()

    area = "국내" if country == "in" else "해외"

    prompt = f"""
당신은 여행 전문가입니다.

사용자가 {area} 여행을 원합니다.

원하는 여행 스타일:
{feeling}

실존하는 여행지 3곳 추천

형식:

1. 여행지명
- 추천 이유

2. 여행지명
- 추천 이유

3. 여행지명
- 추천 이유

100자 이내
"""

    try:

        model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

        response = model.generate_content(
            prompt
        )

        return jsonify(
            kakao_text(response.text)
        )

    except Exception as e:

        return jsonify(
            kakao_text(f"오류 발생: {str(e)}")
        )
