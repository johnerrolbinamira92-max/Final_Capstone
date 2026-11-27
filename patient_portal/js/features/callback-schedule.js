const CALLBACK_TIMES = [
  "08:00",
  "08:30",
  "09:00",
  "09:30",
  "10:00",
  "10:30",
  "11:00",
  "11:30",
  "13:00",
  "13:30",
  "14:00",
  "14:30",
  "15:00",
  "15:30",
];

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

function toTimeValue(value) {
  const match = String(value || "").match(/^(\d{2}):(\d{2})/);
  return match ? `${match[1]}:${match[2]}` : "";
}

function isAvailableDate(date) {
  const today = startOfDay(new Date());
  const weekday = date.getDay();
  return date >= today && weekday !== 0 && weekday !== 6;
}

export function initCallbackSchedule({ onSelection, loadBookedSlots }) {
  const calendarDays = document.querySelector("#calendar-days");
  const monthLabel = document.querySelector("#month-label");
  const selectedDateField = document.querySelector("#requested-date");
  const selectedTimeField = document.querySelector("#requested-time");
  const selectedDateLabel = document.querySelector("#selected-date-label");
  const timeSlots = document.querySelector("#time-slots");
  const availabilityStatus = document.querySelector("#slot-availability-status");
  let visibleMonth = startOfMonth(new Date());
  let availabilitySequence = 0;

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

  function renderTimeSlots(hasDate, takenSlots) {
    timeSlots.replaceChildren();

    CALLBACK_TIMES.forEach((time) => {
      const [hour, minute] = time.split(":").map(Number);
      const label = new Date(2000, 0, 1, hour, minute).toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
        hour12: true
      });
      const isTaken = takenSlots.has(time);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "time-slot";
      button.disabled = !hasDate || isTaken;
      const isSelected = hasDate && selectedTimeField.value === time && !isTaken;
      button.setAttribute("aria-pressed", String(isSelected));

      if (isTaken) {
        button.classList.add("taken");
        button.title = "Already reserved by another patient";
        button.setAttribute("aria-label", `${label}, Taken`);
        const timeLabel = document.createElement("span");
        timeLabel.className = "time-slot-label";
        timeLabel.textContent = label;
        const badge = document.createElement("span");
        badge.className = "time-slot-badge";
        badge.textContent = "Taken";
        button.append(timeLabel, badge);
      } else {
        button.textContent = label;
        if (isSelected) button.classList.add("selected");
        button.addEventListener("click", () => {
          timeSlots.querySelectorAll(".time-slot").forEach((slot) => {
            slot.classList.remove("selected");
            slot.setAttribute("aria-pressed", "false");
          });
          button.classList.add("selected");
          button.setAttribute("aria-pressed", "true");
          selectedTimeField.value = time;
        });
      }

      timeSlots.append(button);
    });
  }

  async function fetchTakenSlots(dateValue) {
    try {
      const rows = await loadBookedSlots(dateValue);
      return new Set(
        (rows || [])
          .filter((row) => row.requested_date === dateValue)
          .map((row) => toTimeValue(row.requested_time_slot))
          .filter(Boolean)
      );
    } catch (error) {
      console.warn("Could not check callback slot availability; booking remains available.", error);
      return new Set();
    }
  }

  async function renderTimes({ clearSelection = false } = {}) {
    const dateValue = selectedDateField.value;
    const requestSequence = ++availabilitySequence;
    if (clearSelection) selectedTimeField.value = "";
    const hasDate = Boolean(dateValue);
    selectedDateLabel.textContent = hasDate
      ? new Date(`${dateValue}T12:00:00`).toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric"
      })
      : "Choose a weekday";
    availabilityStatus.hidden = !hasDate;
    renderTimeSlots(false, new Set());
    if (!hasDate) return;

    const takenSlots = await fetchTakenSlots(dateValue);
    if (requestSequence !== availabilitySequence || selectedDateField.value !== dateValue) return;

    availabilityStatus.hidden = true;
    if (takenSlots.has(selectedTimeField.value)) selectedTimeField.value = "";
    renderTimeSlots(true, takenSlots);
  }

  function selectDate(date) {
    selectedDateField.value = toDateValue(date);
    onSelection();
    renderCalendar();
    renderTimes({ clearSelection: true });
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
      renderTimes({ clearSelection: true });
    },
    reset() {
      selectedDateField.value = "";
      renderCalendar();
      renderTimes({ clearSelection: true });
    },
    async isSlotAvailable(dateValue, timeValue) {
      const requestSequence = ++availabilitySequence;
      if (selectedDateField.value === dateValue) {
        availabilityStatus.hidden = false;
        renderTimeSlots(false, new Set());
      }
      const takenSlots = await fetchTakenSlots(dateValue);
      if (requestSequence === availabilitySequence && selectedDateField.value === dateValue) {
        if (takenSlots.has(timeValue)) selectedTimeField.value = "";
        availabilityStatus.hidden = true;
        renderTimeSlots(true, takenSlots);
      }
      return !takenSlots.has(timeValue);
    }
  };
}
