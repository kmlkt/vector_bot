"""
Расчет профиля ученика по событиям.

Чистые функции: ни базы, ни MAX, ни состояния. На вход — события и справочник
заданий, на выход — числа. Вызывается из /profile (ученик) и /report (учитель).

Модель (спецификация MVP, раздел 4). Пять осей по Климову:
    H — человек–человек (Люди)
    T — человек–техника (Техника)
    S — человек–знак (Знаки)
    I — человек–образ (Образы)
    N — человек–природа (Природа)

Для каждой оси a:
    shown_a    — сколько раз задание оси a было среди трех показанных карточек
    chosen_a   — сколько раз ученик выбрал задание оси a
    checked_a  — сколько проверяемых заданий оси a ученик решил (есть is_correct)
    correct_a  — сколько из них решил верно

    preference_a = chosen_a / shown_a          (0, если shown_a == 0)
    success_a    = correct_a / checked_a       (1, если checked_a == 0)

    score_a = preference_a * (0.6 + 0.4 * success_a)

Успешность не добавляется к склонности, а корректирует ее: верные ответы
оставляют оценку равной склонности, неверные снижают ее до 0.6 от склонности.

Если проверяемых данных по оси нет, множитель берется как средний по тем осям,
где проверка была. Раньше в этом случае множитель равнялся 1, и получалось, что
ось «Люди» — а она непроверяемая целиком, в банке нет ни одного задания с
правильным ответом — всегда получала максимум, тогда как остальные оси теряли
на каждой ошибке. На синтетике с равной склонностью «Люди» выходили в среднем
на 17% выше самой низкой оси и становились ведущими у 24% ровных учеников.
Это противоречило главному свойству формулы, ради которого ее и выбрали:
при равной склонности все оси должны быть равны. Средний множитель означает
честное «про эту ось мы не знаем, поэтому не даем ни бонуса, ни штрафа».

Почему так, а не «0.6 * склонность + 0.4 * успешность» из первой версии спеки:
аддитивная формула при равной склонности давала проверяемым осям больше
(успешность прибавляла до 0.4), и у всех учеников появлялся бы ложный уклон
в «Знаки» и «Технику». Мультипликативная формула этого лишена: при равной
склонности все оси равны, потолок у всех 1.0.

Выраженность профиля: distinct = max(score) - mean(остальных четырех).
Профиль считается выраженным при distinct >= DISTINCT_THRESHOLD и
solved_total >= MIN_SOLVED_FOR_DISTINCT.

Ведущие оси: ось с максимальным score; вторая добавляется, если отстает
не больше чем на LEADING_GAP.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

AXES: tuple[str, ...] = ("H", "T", "S", "I", "N")

AXIS_NAMES: dict[str, str] = {
    "H": "Люди",
    "T": "Техника",
    "S": "Знаки",
    "I": "Образы",
    "N": "Природа",
}

PREFERENCE_WEIGHT = 0.6
SUCCESS_WEIGHT = 0.4

# Порог выбран по замеру на синтетике, где заложенный характер известен заранее
# (validate_model.py, 200 учеников на характер, усреднено по трем прогонам). Колонки: сколько характерных
# учеников получат вывод о себе, скольким ровным мы ошибочно скажем «профиль
# выражен», какова точность вывода у тех, кому он выдан.
#   0.25 — 84% / 31% / 89%
#   0.30 — 75% / 16% / 91%     <- выбрано
#   0.35 — 61% /  8% / 94%
# Ложный вывод дороже отсутствия вывода: ребенок воспринимает его всерьез и
# может на нем что-то решить, а «картина пока ровная» его ни к чему не толкает.
DISTINCT_THRESHOLD = 0.30      # разрыв ведущей оси с остальными
MIN_SOLVED_FOR_DISTINCT = 10   # минимум решенных заданий для «выраженного» профиля
MIN_SOLVED_FOR_PROFILE = 5     # минимум решенных заданий, чтобы показать профиль вообще
LEADING_GAP = 0.1              # вторая ось считается ведущей, если отстает не больше чем на это
FLAT_THRESHOLD = 0.1           # если разрыв меньше — профиль «плоский», выводов не делаем

EVENT_SHOWN = "shown"
EVENT_CHOSEN = "chosen"
EVENT_ANSWERED = "answered"


@dataclass(frozen=True)
class TaskInfo:
    """Минимум о задании, нужный для расчета."""
    axis: str
    checkable: bool


@dataclass(frozen=True)
class AxisStats:
    shown: int = 0
    chosen: int = 0
    solved: int = 0      # все решенные, включая непроверяемые
    checked: int = 0     # решенные проверяемые (есть is_correct)
    correct: int = 0

    @property
    def preference(self) -> float:
        return self.chosen / self.shown if self.shown else 0.0

    @property
    def success(self) -> float | None:
        """None, если проверяемых решенных заданий по оси нет."""
        return self.correct / self.checked if self.checked else None

    def score_with(self, fallback_success: float | None) -> float:
        """Оценка по оси. fallback_success — средняя успешность ученика по
        остальным осям, ею замещается неизвестная успешность этой оси."""
        succ = self.success
        if succ is None:
            succ = fallback_success
        factor = 1.0 if succ is None else PREFERENCE_WEIGHT + SUCCESS_WEIGHT * succ
        return self.preference * factor

    @property
    def score(self) -> float:
        """Оценка без контекста: неизвестная успешность не штрафуется.
        В профиле используется score_with, здесь — для отладки одной оси."""
        return self.score_with(None)


@dataclass(frozen=True)
class Profile:
    scores: dict[str, float]          # ось -> 0..1
    stats: dict[str, AxisStats]
    solved_total: int

    @property
    def distinct(self) -> float:
        """Разрыв между ведущей осью и средним остальных."""
        ordered = sorted(self.scores.values(), reverse=True)
        return ordered[0] - mean(ordered[1:])

    @property
    def is_ready(self) -> bool:
        """Достаточно ли заданий, чтобы показывать профиль."""
        return self.solved_total >= MIN_SOLVED_FOR_PROFILE

    @property
    def is_distinct(self) -> bool:
        """Выраженный профиль: разрыв достаточный и заданий достаточно."""
        return (
            self.solved_total >= MIN_SOLVED_FOR_DISTINCT
            and self.distinct >= DISTINCT_THRESHOLD
        )

    @property
    def is_flat(self) -> bool:
        return self.distinct < FLAT_THRESHOLD


# --------------------------------------------------------------------------
# Доступ к полям события: принимаем и dict, и объект с атрибутами,
# чтобы не зависеть от того, как именно слой данных отдает строки.
# --------------------------------------------------------------------------

def _field(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(name, default)
    return getattr(event, name, default)


def _split_task_ids(task_id: Any) -> list[str]:
    """Для события shown task_id — три id через запятую."""
    if not task_id:
        return []
    return [t.strip() for t in str(task_id).split(",") if t.strip()]


def _tasks_map(tasks: Mapping[str, TaskInfo] | Iterable[Any]) -> dict[str, TaskInfo]:
    """Принимает либо готовый словарь id -> TaskInfo, либо список заданий
    в формате tasks.json (dict с полями id, axis, checkable)."""
    if isinstance(tasks, Mapping):
        return dict(tasks)
    result: dict[str, TaskInfo] = {}
    for t in tasks:
        tid = _field(t, "id")
        result[str(tid)] = TaskInfo(axis=str(_field(t, "axis")), checkable=bool(_field(t, "checkable")))
    return result


# --------------------------------------------------------------------------
# Основные функции
# --------------------------------------------------------------------------

def profile(events: Iterable[Any], tasks: Mapping[str, TaskInfo] | Iterable[Any]) -> Profile:
    """Профиль ученика по его событиям.

    events — строки таблицы events этого ученика (любой порядок):
        type: shown | chosen | answered
        task_id: id задания; для shown — три id через запятую
        is_correct: для answered проверяемого — True/False, иначе None
    tasks — справочник заданий: dict id -> TaskInfo или список из tasks.json.

    События с неизвестным task_id пропускаются: задание могли удалить из банка,
    и это не должно ронять расчет.
    """
    tmap = _tasks_map(tasks)
    counters: dict[str, dict[str, int]] = {a: dict(shown=0, chosen=0, solved=0, checked=0, correct=0) for a in AXES}

    for e in events:
        etype = _field(e, "type")
        if etype == EVENT_SHOWN:
            for tid in _split_task_ids(_field(e, "task_id")):
                info = tmap.get(tid)
                if info and info.axis in counters:
                    counters[info.axis]["shown"] += 1
        elif etype == EVENT_CHOSEN:
            info = tmap.get(str(_field(e, "task_id")))
            if info and info.axis in counters:
                counters[info.axis]["chosen"] += 1
        elif etype == EVENT_ANSWERED:
            info = tmap.get(str(_field(e, "task_id")))
            if not info or info.axis not in counters:
                continue
            c = counters[info.axis]
            c["solved"] += 1
            is_correct = _field(e, "is_correct")
            if info.checkable and is_correct is not None:
                c["checked"] += 1
                if bool(is_correct):
                    c["correct"] += 1

    stats = {a: AxisStats(**counters[a]) for a in AXES}
    known = [s.success for s in stats.values() if s.success is not None]
    fallback = mean(known) if known else None
    scores = {a: round(stats[a].score_with(fallback), 4) for a in AXES}
    solved_total = sum(s.solved for s in stats.values())
    return Profile(scores=scores, stats=stats, solved_total=solved_total)


def leading_axes(p: Profile) -> list[str]:
    """Одна или две ведущие оси. Пустой список, если профиль плоский."""
    if p.is_flat:
        return []
    ordered = sorted(AXES, key=lambda a: p.scores[a], reverse=True)
    first, second = ordered[0], ordered[1]
    if p.scores[first] - p.scores[second] <= LEADING_GAP:
        return [first, second]
    return [first]


def average_profile(profiles: Sequence[Profile]) -> dict[str, float]:
    """Средний профиль по группе (для /report). Пустая группа — нули."""
    if not profiles:
        return {a: 0.0 for a in AXES}
    return {a: round(mean(p.scores[a] for p in profiles), 4) for a in AXES}


def leading_match(a: Profile, b: Profile) -> bool:
    """Совпадает ли ведущая ось между двумя замерами.
    Метрика устойчивости для пилота: считаем долю учеников, у которых True."""
    la, lb = leading_axes(a), leading_axes(b)
    if not la or not lb:
        return False
    return la[0] == lb[0]


# --------------------------------------------------------------------------
# Представление для сообщений бота
# --------------------------------------------------------------------------

def render_bar(score: float, width: int = 10) -> str:
    filled = round(max(0.0, min(1.0, score)) * width)
    return "█" * filled + "░" * (width - filled)


def render_percent(score: float) -> int:
    """Оценка для показа человеку: целые проценты, без знаков после запятой."""
    return round(max(0.0, min(1.0, score)) * 100)


def render_profile_lines(p: Profile, sort: bool = True) -> list[str]:
    """Строки вида «████████░░ 75% Люди».

    Полоска идет первой, поэтому все строки выровнены по левому краю и
    картинка не разъезжается в пропорциональном шрифте (в вебе MAX
    моноширинный текст не применяется). Числа — целые проценты, чтобы не
    было вопроса про знаки после запятой и про точку с запятой.
    По умолчанию оси отсортированы по убыванию: получается рейтинг.
    """
    axes = sorted(AXES, key=lambda a: -p.scores[a]) if sort else list(AXES)
    return [
        f"{render_bar(p.scores[a])} {render_percent(p.scores[a]):>3}%  {AXIS_NAMES[a]}"
        for a in axes
    ]


def summary_key(p: Profile) -> str:
    """Какой текст резюме брать из texts.md."""
    lead = leading_axes(p)
    if not lead:
        return "profile.summary.flat"
    return "profile.summary.one_axis" if len(lead) == 1 else "profile.summary.two_axes"


# --------------------------------------------------------------------------
# Подборка направлений (data/directions.json)
# --------------------------------------------------------------------------
#
# Справочник: список записей {id, kind, title, axes, hint}.
#   kind  — "profile10" (профиль 10 класса) или "college" (специальность СПО)
#   axes  — одна или две оси; первая — главная.
#
# Ранг записи для ведущих осей ученика lead (1 или 2 оси, первая — сильнее):
#   +4  главная ось записи совпадает с первой ведущей осью ученика
#   +2  главная ось записи есть среди ведущих осей ученика (но не первая)
#   +1  вторая ось записи есть среди ведущих осей ученика
# Записи с рангом 0 не показываем. Среди равных — порядок как в файле,
# со сдвигом на salt (например, внутренний id ученика), чтобы у разных
# учеников с одинаковым профилем подборки различались.
#
# В подборку из n стараемся включить хотя бы один профиль 10 класса и
# хотя бы одну специальность колледжа — для 8–9 класса важны обе развилки.

def direction_rank(direction: Mapping[str, Any], lead: Sequence[str]) -> int:
    axes = list(direction.get("axes", []))
    if not axes or not lead:
        return 0
    rank = 0
    if axes[0] == lead[0]:
        rank += 4
    elif axes[0] in lead:
        rank += 2
    if len(axes) > 1 and axes[1] in lead:
        rank += 1
    return rank


def pick_directions(
    lead: Sequence[str],
    directions: Iterable[Mapping[str, Any]],
    n: int = 3,
    salt: int = 0,
) -> list[dict[str, Any]]:
    """До n направлений под ведущие оси. Пустой список, если осей нет."""
    if not lead or n <= 0:
        return []
    ranked = [(direction_rank(d, lead), i, d) for i, d in enumerate(directions)]
    ranked = [(r, i, d) for r, i, d in ranked if r > 0]
    if not ranked:
        return []

    # сдвиг внутри групп равного ранга
    by_rank: dict[int, list] = {}
    for r, i, d in ranked:
        by_rank.setdefault(r, []).append(d)
    ordered: list[dict[str, Any]] = []
    for r in sorted(by_rank, reverse=True):
        group = by_rank[r]
        k = salt % len(group) if group else 0
        ordered.extend(group[k:] + group[:k])

    picked: list[dict[str, Any]] = []
    for kind in ("profile10", "college"):
        for d in ordered:
            if d.get("kind") == kind and d not in picked:
                picked.append(d)
                break
    for d in ordered:
        if len(picked) >= n:
            break
        if d not in picked:
            picked.append(d)
    return picked[:n]


def direction_titles(lead: Sequence[str], directions: Iterable[Mapping[str, Any]],
                     n: int = 3, salt: int = 0) -> list[str]:
    """Заголовки для profile.directions в texts.md."""
    return [d["title"] for d in pick_directions(lead, directions, n=n, salt=salt)]
