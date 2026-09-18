import os

from dotenv import load_dotenv
from flask import Flask

from migration import apply_all_migrations

load_dotenv()

apply_all_migrations()

app = Flask(__name__)

print(os.environ)
BOT_TOKEN = os.environ["BOT_TOKEN"]


@app.route("/")
def hello_world():
    return f"App is running. It uses token: {BOT_TOKEN}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
