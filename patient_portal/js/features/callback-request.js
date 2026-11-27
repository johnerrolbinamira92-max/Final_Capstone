function validateContact(value) {
  const digits = value.replace(/\D/g, "");
  return /^(09\d{9}|639\d{9}|9\d{9})$/.test(digits);
}

function validateHelpRequest() {
  const name = document.querySelector("#patient-name").value.trim();
  const ageValue = document.querySelector("#patient-age").value.trim();
  const age = ageValue ? Number(ageValue) : null;
  const contact = document.querySelector("#patient-contact").value.trim();
  const date = document.querySelector("#requested-date").value;
  const time = document.querySelector("#requested-time").value;
  const consent = document.querySelector("#consent").checked;

  if (name.length > 160) return "Enter a name up to 160 characters.";
  if (age !== null && (!Number.isInteger(age) || age < 1 || age > 120)) {
    return "Enter a valid age between 1 and 120.";
  }
  if (!validateContact(contact)) return "Enter a valid Philippine mobile number.";
  if (!date) return "Choose an available weekday for the callback.";
  if (!time) return "Choose an available callback time.";
  if (!consent) return "Please provide consent before sending your help request.";
  return "";
}

function getMissingColumn(error) {
  if (!["42703", "PGRST204"].includes(error.code)) return null;
  const message = `${error.message || ""} ${error.details || ""}`;
  const match = message.match(
    /(?:column\s+(?:["']?[a-z_][\w]*["']?\.)?["']?([a-z_][\w]*)["']?(?:\s+of\s+relation\s+["']?[a-z_][\w]*["']?)?\s+does not exist|could not find the ["']([a-z_][\w]*)["'] column)/i
  );
  return match ? match[1] || match[2] : null;
}

async function postHelpRequest(config, session, payload) {
  const optionalColumns = new Set([
    "guest_token",
    "patient_name",
    "patient_age",
    "patient_user_id"
  ]);
  const requestPayload = { ...payload };

  while (true) {
    const response = await fetch(`${config.supabaseUrl.replace(/\/$/, "")}/rest/v1/patient_help_requests`, {
      method: "POST",
      headers: {
        apikey: config.supabaseAnonKey,
        Authorization: `Bearer ${session ? session.access_token : config.supabaseAnonKey}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal"
      },
      body: JSON.stringify(requestPayload)
    });

    if (response.ok) return;

    const responseText = await response.text();
    let error;
    try {
      const parsed = JSON.parse(responseText);
      error = parsed && typeof parsed === "object"
        ? parsed
        : { message: responseText };
    } catch {
      error = { message: responseText };
    }

    console.error("Supabase rejected the callback request.", {
      message: error.message,
      details: error.details,
      code: error.code
    });

    const missingColumn = getMissingColumn(error);
    if (
      !missingColumn ||
      !optionalColumns.has(missingColumn) ||
      !Object.prototype.hasOwnProperty.call(requestPayload, missingColumn)
    ) {
      throw new Error("The request could not be sent. Please try again or call the center.");
    }

    delete requestPayload[missingColumn];
  }
}

export async function sendHelpRequest({
  form,
  messageField,
  session,
  guestToken,
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

  const patientName = document.querySelector("#patient-name").value.trim();
  const ageValue = document.querySelector("#patient-age").value.trim();
  const payload = {
    patient_name: patientName || null,
    patient_age: ageValue ? Number(ageValue) : null,
    contact_number: document.querySelector("#patient-contact").value.trim(),
    message: messageField.value.trim(),
    patient_user_id: session ? session.user.id : null,
    ...(guestToken ? { guest_token: guestToken } : {}),
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
    await postHelpRequest(config, session, payload);
    onSuccess();
  } catch (error) {
    console.error("Could not send callback request.", error);
    showFeedback(error.message || "The request could not be sent. Please call the center for help.", "error");
  } finally {
    form.removeAttribute("aria-busy");
    form.querySelectorAll("input, textarea, button").forEach((field) => {
      field.disabled = false;
    });
    const currentFlow = form.querySelector('input[name="next-step"]:checked')?.value;
    submitButton.disabled = !currentFlow;
    submitButton.innerHTML = currentFlow === "help"
      ? 'Send my help request <span aria-hidden="true">›</span>'
      : currentFlow === "private"
        ? 'Store my private entry <span aria-hidden="true">›</span>'
        : "Choose an option to continue";
  }
}
