import os
import sqlite3

from dotenv import load_dotenv
from flask import Flask

from database import Class, User
from migration import apply_all_migrations
from model import UserRole

load_dotenv()
BOT_TOKEN = os.environ["BOT_TOKEN"]

database = sqlite3.connect("storage/database.db")

apply_all_migrations(database)

teacher = User.from_max_id(database, "ttt")
teacher.role = UserRole.TEACHER
Class.create(teacher)
clas = teacher.current_created_class
clas.grade = 7
clas.size = 10

student = User.from_max_id(database, "sss")
student.role = UserRole.STUDENT
student.clas = Class.from_code(database, clas.code)
student.number_in_class = 1


app = Flask(__name__)


@app.route("/")
def hello_world():
    return "App is running."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
