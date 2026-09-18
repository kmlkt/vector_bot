import os

from dotenv import load_dotenv
from flask import Flask

from database import Class, User
from migration import apply_all_migrations
from model import UserRole

load_dotenv()
BOT_TOKEN = os.environ["BOT_TOKEN"]

apply_all_migrations()

teacher = User.from_max_id("ttt")
teacher.role = UserRole.TEACHER
Class.create(teacher)
clas = teacher.current_created_class
clas.grade = 7
clas.size = 10

student = User.from_max_id("sss")
student.role = UserRole.STUDENT
student.clas = Class.from_code(clas.code)
student.number_in_class = 1


app = Flask(__name__)


@app.route("/")
def hello_world():
    return f"App is running. It uses token: {BOT_TOKEN}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
