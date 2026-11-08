(() => {
  "use strict";

  const RETENTION_DAYS = 30;
  const STORAGE_KEY = "hfrc-private-entries-v1";
  const CALLBACK_TIMES = [];
  for (let hour = 9; hour <= 16; hour += 1) {
    CALLBACK_TIMES.push(`${String(hour).padStart(2, "0")}:00`);
    CALLBACK_TIMES.push(`${String(hour).padStart(2, "0")}:30`);
  }

  const form = document.querySelector("#entry-form");
  const messageField = document.querySelector("#message");
  const countLabel = document.querySelector("#character-count");
  const callbackPanel = document.querySelector("#callback-panel");
  const privatePanel = document.querySelector("#private-note-panel");
  const submitButton = document.querySelector("#submit-button");
  const feedback = document.querySelector("#form-message");
  const calendarDays = document.querySelector("#calendar-days");
  const monthLabel = document.querySelector("#month-label");
  const selectedDateField = document.querySelector("#requested-date");
  const selectedTimeField = document.querySelector("#requested-time");
  const selectedDateLabel = document.querySelector("#selected-date-label");
  const timeSlots = document.querySelector("#time-slots");
  let storageUnavailable = false;
  let visibleMonth = startOfMonth(new Date());
  let entries = loadEntries();

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

  function escapeHtml(value) {
    return value.replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[character]);
  }

  function loadEntries() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      if (!Array.isArray(saved)) return [];
      const cutoff = Date.now() - RETENTION_DAYS * 24 * 60 * 60 * 1000;
      const active = saved.filter((entry) =>
        entry && typeof entry.text === "string" &&
        Number.isFinite(entry.createdAt) && entry.createdAt >= cutoff
      );
      localStorage.setItem(STORAGE_KEY, JSON.stringify(active));
      return active;
    } catch (error) {
      console.error("Could not read private entries from this device.", error);
      storageUnavailable = true;
      return [];
    }
  }

  function saveEntries() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
      return true;
    } catch (error) {
      console.error("Could not save private entry to this device.", error);
      showFeedback("This browser could not save your entry. Check available device storage and try again.", "error");
      return false;
    }
  }

  function showFeedback(text, type) {
    feedback.textContent = text;
    feedback.className = `form-message ${type}`;
    feedback.hidden = false;
  }

  function hideFeedback() {
    feedback.hidden = true;
    feedback.textContent = "";
    feedback.className = "form-message";
  }

  function renderHistory() {
    const history = document.querySelector("#entry-history");
    if (!entries.length) {
      history.innerHTML = '<div class="empty-history"><span aria-hidden="true">♙</span><strong>No active private entries on this device.</strong><p>Private entries you save will appear here for up to 30 days.</p></div>';
      return;
    }
    history.innerHTML = entries
      .slice()
      .sort((a, b) => b.createdAt - a.createdAt)
      .map((entry) => {
        const remaining = Math.max(0, RETENTION_DAYS - Math.floor((Date.now() - entry.createdAt) / (24 * 60 * 60 * 1000)));
        const created = new Date(entry.createdAt).toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short"
        });
        return `<article class="entry-card">
          <div class="entry-card-top"><span class="entry-badge">Private release</span><span>${remaining} day${remaining === 1 ? "" : "s"} left</span></div>
          <p class="entry-copy">${escapeHtml(entry.text)}</p>
          <div class="entry-card-bottom"><span>${escapeHtml(created)}<br>Saved on this device</span><button type="button" class="remove-entry" data-entry-id="${escapeHtml(entry.id)}">Remove</button></div>
        </article>`;
      }).join("");
  }

  function isAvailableDate(date) {
    const today = startOfDay(new Date());
    const weekday = date.getDay();
    return date >= today && weekday !== 0 && weekday !== 6;
  }

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

    const currentMonth = startOfMonth(new Date());
    document.querySelector("#previous-month").disabled =
      visibleMonth <= currentMonth;
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
    hideFeedback();
    renderCalendar();
    renderTimes();
  }

  function setFlow(value) {
    const isHelp = value === "help";
    callbackPanel.hidden = !isHelp;
    privatePanel.hidden = isHelp;
    submitButton.innerHTML = isHelp
      ? 'Send my help request <span aria-hidden="true">›</span>'
      : 'Store my private entry <span aria-hidden="true">›</span>';
    submitButton.disabled = false;
    submitButton.classList.toggle("private-submit", !isHelp);
    hideFeedback();
  }

  function validateContact(value) {
    const digits = value.replace(/\D/g, "");
    return /^(09\d{9}|639\d{9}|9\d{9})$/.test(digits);
  }

  function validateHelpRequest() {
    const name = document.querySelector("#patient-name").value.trim();
    const age = Number(document.querySelector("#patient-age").value);
    const contact = document.querySelector("#patient-contact").value.trim();
    const date = selectedDateField.value;
    const time = selectedTimeField.value;
    const consent = document.querySelector("#consent").checked;

    if (!name || name.length > 160) return "Enter your name (up to 160 characters).";
    if (!Number.isInteger(age) || age < 1 || age > 120) return "Enter a valid age between 1 and 120.";
    if (!validateContact(contact)) return "Enter a valid Philippine mobile number.";
    if (!date) return "Choose an available weekday for the callback.";
    if (!time) return "Choose an available callback time.";
    if (!consent) return "Please provide consent before sending your help request.";
    return "";
  }

  async function sendHelpRequest() {
    const validationMessage = validateHelpRequest();
    if (validationMessage) {
      showFeedback(validationMessage, "error");
      return;
    }

    const config = window.PATIENT_PORTAL_CONFIG || {};
    if (!config.supabaseUrl || config.supabaseUrl.includes("YOUR-PROJECT") ||
        !config.supabaseAnonKey || config.supabaseAnonKey.includes("YOUR_SUPABASE")) {
      showFeedback("The portal is not connected yet. Add the Supabase project URL and publishable/anon key to config.js, then try again.", "error");
      return;
    }

    const payload = {
      patient_name: document.querySelector("#patient-name").value.trim(),
      patient_age: Number(document.querySelector("#patient-age").value),
      contact_number: document.querySelector("#patient-contact").value.trim(),
      message: messageField.value.trim(),
      requested_date: selectedDateField.value,
      requested_time_slot: selectedTimeField.value,
      consent_given: true
    };

    form.setAttribute("aria-busy", "true");
    form.querySelectorAll("input, textarea, button").forEach((field) => {
      field.disabled = true;
    });
    submitButton.textContent = "Sending securely…";
    hideFeedback();
    try {
      const response = await fetch(`${config.supabaseUrl.replace(/\/$/, "")}/rest/v1/patient_help_requests`, {
        method: "POST",
        headers: {
          "apikey": config.supabaseAnonKey,
          "Authorization": `Bearer ${config.supabaseAnonKey}`,
          "Content-Type": "application/json",
          "Prefer": "return=minimal"
        },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const details = await response.text();
        console.error("Supabase rejected the callback request.", response.status, details);
        throw new Error("The request could not be sent. Please check your connection and try again, or call the center.");
      }
      form.reset();
      selectedDateField.value = "";
      selectedTimeField.value = "";
      setFlow("help");
      showFeedback("Your help request was sent securely. Center staff will contact you about the schedule you selected.", "success");
      renderCalendar();
      renderTimes();
      countLabel.textContent = "0 / 10,000";
    } catch (error) {
      console.error("Could not send callback request.", error);
      showFeedback(error.message || "The request could not be sent. Please call the center for help.", "error");
    } finally {
      form.removeAttribute("aria-busy");
      form.querySelectorAll("input, textarea, button").forEach((field) => {
        field.disabled = false;
      });
      submitButton.disabled = false;
      const currentFlow = form.querySelector('input[name="next-step"]:checked').value;
      submitButton.innerHTML = currentFlow === "help"
        ? 'Send my help request <span aria-hidden="true">›</span>'
        : 'Store my private entry <span aria-hidden="true">›</span>';
    }
  }

  document.querySelectorAll('input[name="next-step"]').forEach((input) => {
    input.addEventListener("change", () => setFlow(input.value));
  });

  messageField.addEventListener("input", () => {
    countLabel.textContent = `${messageField.value.length.toLocaleString()} / 10,000`;
    hideFeedback();
  });

  document.querySelector("#previous-month").addEventListener("click", () => {
    visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() - 1, 1);
    renderCalendar();
  });
  document.querySelector("#next-month").addEventListener("click", () => {
    visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 1);
    renderCalendar();
  });

  document.querySelector("#theme-toggle").addEventListener("click", (event) => {
    const light = document.body.classList.toggle("light-theme");
    event.currentTarget.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
  });

  document.querySelector("#entry-history").addEventListener("click", (event) => {
    const button = event.target.closest("[data-entry-id]");
    if (!button) return;
    entries = entries.filter((entry) => entry.id !== button.dataset.entryId);
    if (saveEntries()) renderHistory();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const mode = form.querySelector('input[name="next-step"]:checked').value;
    const text = messageField.value.trim();
    if (!text) {
      showFeedback("Write a little about what’s on your mind before continuing.", "error");
      messageField.focus();
      return;
    }
    if (mode === "help") {
      await sendHelpRequest();
      return;
    }

    entries.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      text,
      createdAt: Date.now()
    });
    if (!saveEntries()) return;
    renderHistory();
    form.reset();
    form.querySelector('input[name="next-step"][value="private"]').checked = true;
    countLabel.textContent = "0 / 10,000";
    setFlow("private");
    showFeedback("Your private entry was saved on this device only. It will be removed from this list after 30 days.", "success");
  });

  document.querySelector("#theme-toggle").setAttribute("aria-label", "Switch to light theme");
  renderCalendar();
  renderTimes();
  renderHistory();
  if (storageUnavailable) {
    showFeedback("This browser could not access device storage. Private entries cannot be saved here.", "error");
  }
})();
