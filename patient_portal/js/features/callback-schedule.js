const CALLBACK_TIMES = [];
for (let hour = 9; hour <= 16; hour += 1) {
  CALLBACK_TIMES.push(`${String(hour).padStart(2, "0")}:00`);
  CALLBACK_TIMES.push(`${String(hour).padStart(2, "0")}:30`);
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function toDateValue(date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function isAvailableDate(date) {
  const today = startOfDay(new Date());
  const weekday = date.getDay();
  return date >= today && weekday !== 0 && weekday !== 6;
}

export function initCallbackSchedule({ onSelection }) {
  const calendarDays = document.querySelector("#calendar-days");
  const monthLabel = document.querySelector("#month-label");
  const selectedDateField = document.querySelector("#requested-date");
  const selectedTimeField = document.querySelector("#requested-time");
  const selectedDateLabel = document.querySelector("#selected-date-label");
  const timeSlots = document.querySelector("#time-slots");
  let visibleMonth = startOfMonth(new Date());

  function renderCalendar() {
    monthLabel.textContent = visibleMonth.toLocaleDateString(undefined, {
      month: "long",
      year: "numeric"
    });
    calendarDays.replaceChildren();
    const offset = visibleMonth.getDay();
    const numberOfDays = new Date(
      visibleMonth.getFullYear(),
      visibleMonth.getMonth() + 1,
      0
    ).getDate();

    for (let index = 0; index < offset; index += 1) {
      const blank = document.createElement("span");
      blank.className = "calendar-blank";
      blank.setAttribute("aria-hidden", "true");
      calendarDays.append(blank);
    }

    for (let number = 1; number <= numberOfDays; number += 1) {
      const date = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), number);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "calendar-day";
      button.textContent = String(number);
      button.disabled = !isAvailableDate(date);
      button.setAttribute("aria-label", date.toLocaleDateString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric"
      }));
      if (selectedDateField.value === toDateValue(date)) {
        button.classList.add("selected");
        button.setAttribute("aria-pressed", "true");
      } else {
        button.setAttribute("aria-pressed", "false");
      }
      button.addEventListener("click", () => selectDate(date));
      calendarDays.append(button);
    }

    document.querySelector("#previous-month").disabled =
      visibleMonth <= startOfMonth(new Date());
  }

  function renderTimes() {
    timeSlots.replaceChildren();
    selectedTimeField.value = "";
    const hasDate = Boolean(selectedDateField.value);
    selectedDateLabel.textContent = hasDate
      ? new Date(`${selectedDateField.value}T12:00:00`).toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric"
      })
      : "Choose a weekday";

    CALLBACK_TIMES.forEach((time) => {
      const [hour, minute] = time.split(":").map(Number);
      const label = new Date(2000, 0, 1, hour, minute).toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit"
      });
      const button = document.createElement("button");
      button.type = "button";
      button.className = "time-slot";
      button.textContent = label;
      button.disabled = !hasDate;
      button.setAttribute("aria-pressed", "false");
      button.addEventListener("click", () => {
        timeSlots.querySelectorAll(".time-slot").forEach((slot) => {
          slot.classList.remove("selected");
          slot.setAttribute("aria-pressed", "false");
        });
        button.classList.add("selected");
        button.setAttribute("aria-pressed", "true");
        selectedTimeField.value = time;
      });
      timeSlots.append(button);
    });
  }

  function selectDate(date) {
    selectedDateField.value = toDateValue(date);
    selectedTimeField.value = "";
    onSelection();
    renderCalendar();
    renderTimes();
  }

  document.querySelector("#previous-month").addEventListener("click", () => {
    visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() - 1, 1);
    renderCalendar();
  });
  document.querySelector("#next-month").addEventListener("click", () => {
    visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 1);
    renderCalendar();
  });

  return {
    render() {
      renderCalendar();
      renderTimes();
    },
    reset() {
      selectedDateField.value = "";
      selectedTimeField.value = "";
      renderCalendar();
      renderTimes();
    }
  };
}
