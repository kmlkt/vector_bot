async function loadReport() {
  const response = await fetch(`/report?${window.WebApp?.initData}`);
  if (!response.ok) {
    if (response.status == 401) {
      showError(
        "Сначала откройте чат с ботом",
        "Напишите боту /start и выберите, кто вы. Если вы учитель, после этого создайте класс командой /class и вернитесь сюда",
      );
    } else if (response.status == 403) {
      showError(
        "Здесь отчет для учителя",
        "Ты вошел как ученик. Свой профиль смотри в чате с ботом, команда /profile",
      );
    } else {
      showError(
        "Что-то пошло не так с моей стороны",
        "Попробуйте еще раз через минуту. Если повторится — /help.",
      );
    }
    return;
  }
  const reports = await response.json();
  if (reports.length == 0) {
    showError(
      "У вас пока нет классов",
      "Создайте класс в чате командой /class, потом обновите страницу",
    );
    return;
  }
  renderSelector(
    reports[0],
    reports.map((x) => x.class_code),
    (class_code) => {
      renderReport(reports.find((x) => x.class_code == class_code));
    },
  );
  renderReport(reports[0]);
}

function showError(title, text) {
  document.querySelector("#app").setAttribute("hidden", "");
  document.querySelector("#error").removeAttribute("hidden");
  document.querySelector("#error-title").textContent = title;
  document.querySelector("#error-text").textContent = text;
}

function renderSelector(report, class_codes, change) {
  const select = document.querySelector("#class-code-select");
  select.innerHTML = class_codes
    .map(
      (x) =>
        `<option value="${x}" ${report.class_code == x ? "selected" : ""}>${x}</option>`,
    )
    .join("");
  select.addEventListener("change", (e) => {
    change(e.target.value);
  });
}

// вызов функций для обработки отчёта и отрисовке его в html
function renderReport(report) {
  renderHeader(report);
  renderStats(report);
  renderProfile(report);
  renderStudents(report);
  renderNote(report);
}

// отображение класса и кода класса
function renderHeader(report) {
  document.querySelector("#class-title").textContent = `${report.grade} класс`;
}

// обработка и отображение статистики
function renderStats(report) {
  const stats = document.querySelector("#stats");

  const items = [
    {
      value: report.bound.length,
      label: "Привязано",
    },
    {
      value: report.active,
      label: "Активных",
    },
    {
      value: report.passed_10,
      label: "Прошли 10+",
    },
    {
      value: report.not_started.length,
      label: "Не начинали",
    },
  ];

  stats.innerHTML = "";

  for (const item of items) {
    const card = document.createElement("div");

    card.className = "stat";

    card.innerHTML = `
            <div class="stat-value">${item.value}</div>
            <div class="stat-label">${item.label}</div>
        `;

    stats.appendChild(card);
  }
}

// обработка и отображение статистики по профилям
function renderProfile(report) {
  const profile = document.querySelector("#profile");

  profile.innerHTML = "";

  for (const axis in report.average_profile) {
    const value = report.average_profile[axis];

    const percent = Math.round(value * 100);

    const name = report.axis_names[axis];

    const row = document.createElement("div");

    row.className = "profile-row";

    row.innerHTML = `
            <div class="profile-name">
                ${name}
            </div>

            <div class="profile-bar">
                <div
                    class="profile-fill"
                    style="width: ${percent}%"
                ></div>
            </div>

            <div class="profile-value">
                ${percent}%
            </div>
        `;

    profile.appendChild(row);
  }
}

// обработка и отображение каждого ученика с краткой статистикой
function renderStudents(report) {
  const students = document.querySelector("#students");

  students.innerHTML = "";

  for (const student of report.students) {
    const leading = student.leading
      .map((axis) => report.axis_names[axis])
      .join(", ");

    const status = student.active ? "Активен" : "Неактивен";

    const profileStatus = student.distinct
      ? "Выраженный профиль"
      : "Профиль не выражен";

    const item = document.createElement("div");

    item.className = "student";

    item.innerHTML = `
            <div class="student-number">
                ${student.number}
            </div>

            <div class="student-info">

                <div class="student-main">
                    ${student.solved} заданий
                </div>

                <div class="student-sub">
                    ${leading || "Ведущая ось не определена"}
                    ·
                    ${profileStatus}
                </div>

            </div>

            <div class="student-status">
                ${status}
            </div>
        `;

    students.appendChild(item);
  }
}

// отображение примечание
function renderNote(report) {
  const note = document.querySelector("#note");

  note.textContent = report.note;
}

loadReport();
