from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import urllib.request
import urllib.parse
import ssl
import random

app = Flask(__name__)


@app.route("/", methods=["GET"])
def home():
    return "Server is running."


# 1. 랜덤 숫자 테스트
@app.route("/text", methods=["GET", "POST"])
def text_skill():
    response = {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": str(random.randint(1, 10))
                }
            }]
        }
    }
    return jsonify(response)


# 2. 이미지 테스트
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


# 3. 사용자가 보낸 발화를 그대로 돌려주기
@app.route("/echo", methods=["POST"])
def echo_skill():
    data = request.get_json(silent=True) or {}
    user_input = data.get("userRequest", {}).get("utterance", "입력값이 없습니다.")

    response = {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": user_input
                }
            }]
        }
    }
    return jsonify(response)


# 4. 발화 내용을 네이버 뉴스에서 검색해서 제목 크롤링
@app.route("/naver-news", methods=["POST"])
def naver_news_skill():
    data = request.get_json(silent=True) or {}
    user_input = data.get("userRequest", {}).get("utterance", "").strip()

    if not user_input:
        return jsonify({
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": "검색어가 없습니다."
                    }
                }]
            }
        })

    query = urllib.parse.quote(user_input)
    url = f"https://search.naver.com/search.naver?where=news&query={query}"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select(".news_tit")

        titles = []
        for item in items[:5]:
            titles.append(item.get("title", item.get_text(strip=True)))

        if titles:
            result_text = "\n".join([f"{i+1}. {title}" for i, title in enumerate(titles)])
        else:
            result_text = "검색 결과를 찾지 못했습니다."

    except Exception as e:
        result_text = f"크롤링 중 오류가 발생했습니다: {str(e)}"

    response = {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": result_text[:1000]
                }
            }]
        }
    }
    return jsonify(response)


# 5. 울산 날씨 크롤링
@app.route("/ulsan-weather", methods=["GET", "POST"])
def ulsan_weather_skill():
    try:
        context = ssl._create_unverified_context()
        url = "https://search.naver.com/search.naver?query=%EC%9A%B8%EC%82%B0%20%EB%82%A0%EC%94%A8"

        webpage = urllib.request.urlopen(url, context=context)
        soup = BeautifulSoup(webpage, "html.parser")

        temps = soup.find("div", class_="temperature_text")
        summary = soup.find("p", class_="summary")

        if temps and summary:
            result_text = "울산 " + temps.get_text(strip=True) + " " + summary.get_text(strip=True)
        else:
            result_text = "날씨 정보를 가져오지 못했습니다."

    except Exception as e:
        result_text = f"날씨 조회 중 오류가 발생했습니다: {str(e)}"

    response = {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": result_text[:1000]
                }
            }]
        }
    }
    return jsonify(response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
