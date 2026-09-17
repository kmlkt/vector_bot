from database import (
    AlreadyExistsError,
    Class,
    NotFoundError,
    User,
    ValidationError,
)
from migration import apply_all_migrations
from model import UserRole

apply_all_migrations()

t = User.from_max_id("t")
# При задании роли teacher класс создаётся автоматически, задаётся рандомный код класса
t.role = UserRole.TEACHER
t.clas.grade = 8
t.clas.size = 10

class_code = t.clas.code

# Норм юзер
s1 = User.from_max_id("s1")
s1.role = UserRole.STUDENT
s1.clas = Class.from_code(class_code)
s1.number_in_class = 1

# Плохой юзер
s2 = User.from_max_id("s2")
s2.role = UserRole.STUDENT
try:
    s2.clas = Class.from_code("1I0O")
except NotFoundError:
    print("Класса с таком кодом не существует")
s2.clas = Class.from_code(class_code)
try:
    s2.number_in_class = 0
except ValidationError:
    print("Некорректный номер в классе")
try:
    s2.number_in_class = 11
except ValidationError:
    print("Некорректный номер в классе")
try:
    s2.number_in_class = 1
except AlreadyExistsError:
    print("Номер в классе занят")
s2.number_in_class = 2
