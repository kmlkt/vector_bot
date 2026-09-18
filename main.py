from flask import Flask

from migration import apply_all_migrations

apply_all_migrations()

app = Flask(__name__)


@app.route("/")
def hello_world():
    return "App is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
