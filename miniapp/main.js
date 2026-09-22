// загрузка отчёта из report.json
async function loadReport() {
  const response = await fetch("report.json");
  const report = await response.json();

  renderReport(report);
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

  document.querySelector("#class-code").textContent =
    `Код: ${report.class_code}`;
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
