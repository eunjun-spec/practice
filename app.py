from flask import Flask, jsonify
import sys
import random

app = Flask(__name__)


@app.route('/', methods=["GET", "POST"])
def index():
    response = {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": 

str(random.randint(1,10))
                }
            }]
        }
    }
    return jsonify(response)

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=5000, debug=True)
