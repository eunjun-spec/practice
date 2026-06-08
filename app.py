import os
import random
import requests
import urllib.parse
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

app = Flask(__name__)

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

@app.route("/key-test")
def key_test():
    key = os.getenv("OPENAI_API_KEY")

    if not key:
        return "KEY 없음"

    return f"KEY 존재: {key[:15]}"


@app.route("/travel", methods=["POST"])
def travel():
    data = request.get_json(silent=True) or {}

    country = data.get("action", {}).get("params", {}).get("country", "")

    feeling = data.get("userRequest", {}).get("utterance", "").strip()

    if not feeling:
        return jsonify(kakao_text("원하시는 여행 스타일을 입력해주세요."))

    if country == "in":
        area = "대한민국"
    else:
        area = "해외"

    prompt = f"""
사용자가 {area} 여행을 원합니다.

원하는 여행 스타일:
{feeling}

조건
1. 여행지 3곳 추천
2. 추천 이유 설명
3. 보기 쉽게 작성
4. 100자 이내
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "당신은 전문 여행 플래너입니다."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.8,
            max_tokens=500
        )

        result = response.choices[0].message.content

        return jsonify(kakao_text(result))

    except Exception as e:
        return jsonify(kakao_text(str(e)))
