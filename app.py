import json

from db import (
    init_db,
    save_state,
    get_state,
    clear_state,
    save_schedule,
    get_schedules,
    delete_latest
)

init_db()

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

실존하는 여행지 1곳 추천

형식:

1. 여행지명

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


@app.route("/schedule_create", methods=["POST"])
def schedule_create():

    data = request.get_json(silent=True) or {}

    user_id = (
        data
        .get("userRequest", {})
        .get("user", {})
        .get("id", "guest")
    )

    save_state(
        user_id,
        "date",
        {}
    )

    return jsonify(
        kakao_text(
            "여행 날짜 입력\n예: 2026-08-01~2026-08-03"
        )
    )


@app.route("/schedule_date", methods=["POST"])
def schedule_date():

    data = request.get_json(silent=True) or {}

    user_id = (
        data
        .get("userRequest", {})
        .get("user", {})
        .get("id", "guest")
    )

    text = (
        data
        .get("userRequest", {})
        .get("utterance", "")
        .strip()
    )

    try:
        start, end = text.split("~")

    except:

        return jsonify(
            kakao_text(
                "형식 오류"
            )
        )

    save_state(
        user_id,
        "place",
        {
            "start": start.strip(),
            "end": end.strip(),
            "places": []
        }
    )

    return jsonify(
        kakao_text(
            "장소 입력"
        )
    )


@app.route("/schedule_place", methods=["POST"])
def schedule_place():

    data = request.get_json(silent=True) or {}

    user_id = (
        data
        .get("userRequest", {})
        .get("user", {})
        .get("id", "guest")
    )

    text = (
        data
        .get("userRequest", {})
        .get("utterance", "")
        .strip()
    )

    state = get_state(user_id)

    if not state:

        return jsonify(
            kakao_text(
                "먼저 일정 생성"
            )
        )

    temp = state["temp"]

    temp["places"].append(
        text
    )

    save_state(
        user_id,
        "place",
        temp
    )

    result = []

    for i, p in enumerate(
        temp["places"],
        1
    ):

        result.append(
            f"{i}. {p}"
        )

    return jsonify(
        kakao_text(
            "\n".join(result)
        )
    )


@app.route("/schedule_order", methods=["POST"])
def schedule_order():

    data = request.get_json(silent=True) or {}

    user_id = (
        data
        .get("userRequest", {})
        .get("user", {})
        .get("id", "guest")
    )

    text = (
        data
        .get("userRequest", {})
        .get("utterance", "")
        .strip()
    )

    state = get_state(user_id)

    temp = state["temp"]

    try:

        a, b = map(
            int,
            text.split()
        )

        temp["places"][a-1], temp["places"][b-1] = (
            temp["places"][b-1],
            temp["places"][a-1]
        )

    except:

        return jsonify(
            kakao_text(
                "예: 1 2"
            )
        )

    save_state(
        user_id,
        "place",
        temp
    )

    return jsonify(
        kakao_text(
            "순서 변경 완료"
        )
    )


@app.route("/schedule_save", methods=["POST"])
def schedule_save():

    data = request.get_json(silent=True) or {}

    user_id = (
        data
        .get("userRequest", {})
        .get("user", {})
        .get("id", "guest")
    )

    state = get_state(
        user_id
    )

    temp = (
        state["temp"]
    )

    save_schedule(
        user_id,
        temp["start"],
        temp["end"],
        temp["places"]
    )

    clear_state(
        user_id
    )

    return jsonify(
        kakao_text(
            "저장 완료"
        )
    )


@app.route("/schedule_view", methods=["POST"])
def schedule_view():

    data = request.get_json(silent=True) or {}

    user_id = (
        data
        .get("userRequest", {})
        .get("user", {})
        .get("id", "guest")
    )

    rows = get_schedules(
        user_id
    )

    result = []

    for r in rows:

        places = json.loads(
            r["places"]
        )

        result.append(
            f"""
{r["start_date"]}
~
{r["end_date"]}

{chr(10).join(places)}
"""
        )

    return jsonify(
        kakao_text(
            "\n\n".join(
                result
            )
        )
    )


@app.route("/schedule_delete", methods=["POST"])
def schedule_delete():

    data = request.get_json(silent=True) or {}

    user_id = (
        data
        .get("userRequest", {})
        .get("user", {})
        .get("id", "guest")
    )

    delete_latest(
        user_id
    )

    return jsonify(
        kakao_text(
            "삭제 완료"
        )
    )
