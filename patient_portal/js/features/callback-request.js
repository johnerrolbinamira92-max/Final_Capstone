function validateContact(value) {
  const digits = value.replace(/\D/g, "");
  return /^(09\d{9}|639\d{9}|9\d{9})$/.test(digits);
}

function validateHelpRequest() {
  const name = document.querySelector("#patient-name").value.trim();
  const age = Number(document.querySelector("#patient-age").value);
  const contact = document.querySelector("#patient-contact").value.trim();
  const date = document.querySelector("#requested-date").value;
  const time = document.querySelector("#requested-time").value;
  const consent = document.querySelector("#consent").checked;

  if (!name || name.length > 160) return "Enter your name (up to 160 characters).";
  if (!Number.isInteger(age) || age < 1 || age > 120) return "Enter a valid age between 1 and 120.";
  if (!validateContact(contact)) return "Enter a valid Philippine mobile number.";
  if (!date) return "Choose an available weekday for the callback.";
  if (!time) return "Choose an available callback time.";
  if (!consent) return "Please provide consent before sending your help request.";
  return "";
}

export async function sendHelpRequest({
  form,
  messageField,
  showFeedback,
  hideFeedback,
  onSuccess
}) {
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
    requested_date: document.querySelector("#requested-date").value,
    requested_time_slot: document.querySelector("#requested-time").value,
    consent_given: true
  };

  form.setAttribute("aria-busy", "true");
  form.querySelectorAll("input, textarea, button").forEach((field) => {
    field.disabled = true;
  });
  const submitButton = document.querySelector("#submit-button");
  submitButton.textContent = "Sending securely…";
  hideFeedback();
  try {
    const response = await fetch(`${config.supabaseUrl.replace(/\/$/, "")}/rest/v1/patient_help_requests`, {
      method: "POST",
      headers: {
        apikey: config.supabaseAnonKey,
        Authorization: `Bearer ${config.supabaseAnonKey}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal"
      },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      const details = await response.text();
      console.error("Supabase rejected the callback request.", response.status, details);
      throw new Error("The request could not be sent. Please check your connection and try again, or call the center.");
    }
    onSuccess();
    showFeedback("Your help request was sent securely. Center staff will contact you about the schedule you selected.", "success");
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
