import os
import json
import requests
import urllib.parse

from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

from db import (
    init_db,
    save_state,
    get_state,
    clear_state,
    save_schedule,
    get_schedules,
    delete_latest
)

load_dotenv()

app = Flask(__name__)

genai.configure(
    api_key=os.getenv(
        "GEMINI_API_KEY"
    )
)

init_db()


def kakao_text(text):

    safe_text = (
        text[:950] + "..."
        if len(text) > 950
        else text
    )

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


@app.route(
    "/key-test",
    methods=["GET", "POST"]
)
def key_test():

    key = os.getenv(
        "GEMINI_API_KEY"
    )

    if not key:

        return jsonify(
            kakao_text(
                "KEY 없음"
            )
        )

    return jsonify(
        kakao_text(
            f"KEY 존재: {key[:15]}"
        )
    )


@app.route(
    "/travel",
    methods=["POST"]
)
def travel():

    data = (
        request
        .get_json(
            silent=True
        )
        or {}
    )

    country = (
        data
        .get(
            "action",
            {}
        )
        .get(
            "params",
            {}
        )
        .get(
            "country",
            ""
        )
    )

    feeling = (
        data
        .get(
            "userRequest",
            {}
        )
        .get(
            "utterance",
            ""
        )
        .strip()
    )

    area = (
        "국내"
        if country == "in"
        else "해외"
    )

    prompt = f"""
당신은 여행 전문가입니다.

사용자가 {area} 여행을 원합니다.

원하는 여행 스타일:
{feeling}

실존하는 여행지 2곳 추천

형식:

1. 여행지명

2. 여행지명

다른 설명 없이 출력
"""

    try:

        model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

        response = (
            model
            .generate_content(
                prompt
            )
        )

        return jsonify(
            kakao_text(
                response.text
            )
        )

    except Exception as e:

        return jsonify(
            kakao_text(
                str(e)
            )
        )


@app.route(
    "/schedule_create",
    methods=["POST"]
)
def schedule_create():

    data = (
        request
        .get_json(
            silent=True
        )
        or {}
    )

    user_id = (
        data
        .get(
            "userRequest",
            {}
        )
        .get(
            "user",
            {}
        )
        .get(
            "id",
            "guest"
        )
    )

    save_state(
        user_id,
        "place",
        {
            "start": "",
            "end": "",
            "places": []
        }
    )

    return jsonify(
        kakao_text(
            "여행 날짜를 입력해주세요."
        )
    )


@app.route(
    "/schedule_date",
    methods=["POST"]
)
def schedule_date():

    data = (
        request
        .get_json(
            silent=True
        )
        or {}
    )

    user_id = (
        data["userRequest"]
        ["user"]
        ["id"]
    )

    date = (
        data
        .get(
            "action",
            {}
        )
        .get(
            "params",
            {}
        )
        .get(
            "date",
            ""
        )
    )

    try:

        start, end = (
            date
            .split("~")
        )

    except:

        return jsonify(
            kakao_text(
                "예: 2026-08-01~2026-08-03"
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
            "장소를 계속 입력해주세요."
        )
    )


@app.route(
    "/schedule_place",
    methods=["POST"]
)
def schedule_place():

    data = (
        request
        .get_json(
            silent=True
        )
        or {}
    )

    user_id = (
        data["userRequest"]
        ["user"]
        ["id"]
    )

    place = (
        data
        .get(
            "action",
            {}
        )
        .get(
            "params",
            {}
        )
        .get(
            "place",
            ""
        )
    )

    state = (
        get_state(
            user_id
        )
    )

    if not state:

        return jsonify(
            kakao_text(
                "먼저 일정 생성"
            )
        )

    temp = (
        state["temp"]
    )

    temp["places"].append(
        place
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
            "\n".join(
                result
            )
        )
    )


@app.route(
    "/schedule_order",
    methods=["POST"]
)
def schedule_order():

    data = (
        request
        .get_json(
            silent=True
        )
        or {}
    )

    user_id = (
        data["userRequest"]
        ["user"]
        ["id"]
    )

    params = (
        data
        .get(
            "action",
            {}
        )
        .get(
            "params",
            {}
        )
    )

    try:

        a = int(
            params["from"]
        )

        b = int(
            params["to"]
        )

    except:

        return jsonify(
            kakao_text(
                "번호 오류"
            )
        )

    state = (
        get_state(
            user_id
        )
    )

    temp = (
        state["temp"]
    )

    places = (
        temp["places"]
    )

    places[a - 1], places[b - 1] = (
        places[b - 1],
        places[a - 1]
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


@app.route(
    "/schedule_save",
    methods=["POST"]
)
def schedule_save():

    data = (
        request
        .get_json(
            silent=True
        )
        or {}
    )

    user_id = (
        data["userRequest"]
        ["user"]
        ["id"]
    )

    state = (
        get_state(
            user_id
        )
    )

    if not state:

        return jsonify(
            kakao_text(
                "저장할 일정 없음"
            )
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


@app.route(
    "/schedule_view",
    methods=["POST"]
)
def schedule_view():

    data = (
        request
        .get_json(
            silent=True
        )
        or {}
    )

    user_id = (
        data["userRequest"]
        ["user"]
        ["id"]
    )

    rows = (
        get_schedules(
            user_id
        )
    )

    if not rows:

        return jsonify(
            kakao_text(
                "일정 없음"
            )
        )

    result = []

    for r in rows:

        places = (
            json.loads(
                r["places"]
            )
        )

        result.append(
            f"""
{r["start_date"]}
~
{r["end_date"]}

{" / ".join(places)}
"""
        )

    return jsonify(
        kakao_text(
            "\n\n".join(
                result
            )
        )
    )


@app.route(
    "/schedule_delete",
    methods=["POST"]
)
def schedule_delete():

    data = (
        request
        .get_json(
            silent=True
        )
        or {}
    )

    user_id = (
        data["userRequest"]
        ["user"]
        ["id"]
    )

    delete_latest(
        user_id
    )

    return jsonify(
        kakao_text(
            "최근 일정 삭제 완료"
        )
    )


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
