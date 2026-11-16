(() => {
  const detailDue = document.querySelector("[data-assignment-due]");
  const detailCountdown = document.querySelector("[data-assignment-countdown]");
  if (detailDue && detailCountdown) {
    const dueAt = new Date(detailDue.dataset.assignmentDue).getTime();
    if (!Number.isFinite(dueAt)) {
      detailCountdown.textContent = "Countdown unavailable";
    } else {
      const renderDue = () => {
        const remaining = dueAt - Date.now();
        if (remaining <= 0) {
          detailCountdown.textContent = "Past due";
          return;
        }
        const days = Math.floor(remaining / 86400000);
        const hours = Math.floor((remaining % 86400000) / 3600000);
        detailCountdown.textContent = `${days}d ${hours}h remaining`;
      };
      renderDue();
      window.setInterval(renderDue, 60000);
    }
  }

  const deadline = document.querySelector("[data-next-deadline]");
  const countdown = document.querySelector("[data-deadline-countdown]");
  if (deadline && countdown && deadline.dataset.nextDeadline) {
    const dueAt = new Date(deadline.dataset.nextDeadline).getTime();
    if (!Number.isFinite(dueAt)) {
      countdown.textContent = "Countdown unavailable";
    } else {
      const render = () => {
        const remaining = dueAt - Date.now();
        if (remaining <= 0) {
          countdown.textContent = "Deadline reached";
          return;
        }
        const days = Math.floor(remaining / 86400000);
        const hours = Math.floor((remaining % 86400000) / 3600000);
        countdown.textContent = days ? `${days}d ${hours}h remaining` : `${hours}h ${Math.floor(remaining % 3600000 / 60000)}m remaining`;
      };
      render();
      window.setInterval(render, 60000);
    }
  }

  const calendar = document.querySelector("[data-calendar]");
  if (!calendar) return;
  const grid = calendar.querySelector("[data-calendar-grid]");
  const heading = calendar.querySelector("[data-calendar-title]");
  const assignmentData = JSON.parse(document.getElementById("assignment-due-dates")?.textContent || "{}");
  const monthText = calendar.dataset.month;
  const [year, month] = monthText.split("-").map(Number);
  const first = new Date(year, month - 1, 1);
  const start = new Date(year, month - 1, 1 - first.getDay());
  heading.textContent = first.toLocaleDateString(undefined, {month: "long", year: "numeric"});
  ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].forEach(day => {
    const label = document.createElement("div");
    label.className = "calendar-day-label";
    label.textContent = day;
    grid.append(label);
  });
  for (let index = 0; index < 42; index += 1) {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    const cell = document.createElement("div");
    cell.className = `calendar-day${date.getMonth() !== first.getMonth() ? " outside" : ""}`;
    const day = document.createElement("strong");
    day.textContent = String(date.getDate());
    cell.append(day);
    (assignmentData[key] || []).forEach(item => {
      const link = document.createElement("a");
      link.href = item.url;
      link.textContent = item.title;
      link.title = item.title;
      cell.append(link);
    });
    grid.append(cell);
  }
  calendar.querySelectorAll("[data-month-shift]").forEach(button => button.addEventListener("click", () => {
    const shifted = new Date(year, month - 1 + Number(button.dataset.monthShift), 1);
    const nextMonth = `${shifted.getFullYear()}-${String(shifted.getMonth() + 1).padStart(2, "0")}`;
    const url = new URL(window.location.href);
    url.searchParams.set("month", nextMonth);
    window.location.assign(url);
  }));
})();
