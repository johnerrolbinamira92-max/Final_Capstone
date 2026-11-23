type AppointmentStatusPayload = {
  request_id?: unknown;
  patient_email?: unknown;
  approval_status?: unknown;
  requested_date?: unknown;
  requested_time_slot?: unknown;
  confirmed_date?: unknown;
  confirmed_time_slot?: unknown;
};

function jsonResponse(status: number, body: Record<string, string>) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function secretsMatch(candidate: string, expected: string) {
  let difference = candidate.length ^ expected.length;
  const length = Math.max(candidate.length, expected.length);
  for (let index = 0; index < length; index += 1) {
    difference |= (candidate.charCodeAt(index) || 0) ^ (expected.charCodeAt(index) || 0);
  }
  return difference === 0;
}

function formatDate(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const dateValue = value.trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateValue)) return null;
  const date = new Date(`${dateValue}T12:00:00Z`);
  if (
    Number.isNaN(date.getTime()) ||
    date.toISOString().slice(0, 10) !== dateValue
  ) return null;
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "UTC",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function formatTime(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const match = /^(\d{1,2}):(\d{2})(?::\d{2})?$/.exec(value.trim());
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) return null;
  return new Date(Date.UTC(2000, 0, 1, hour, minute)).toLocaleTimeString("en-US", {
    timeZone: "UTC",
    hour: "numeric",
    minute: "2-digit",
  });
}

Deno.serve(async (request) => {
  if (request.method !== "POST") {
    return jsonResponse(405, { error: "Method not allowed." });
  }

  const expectedSecret = Deno.env.get("WELLNESS_WEBHOOK_SECRET");
  if (!expectedSecret) {
    console.error("WELLNESS_WEBHOOK_SECRET is not configured.");
    return jsonResponse(500, { error: "Notification service is not configured." });
  }

  const suppliedSecret = request.headers.get("x-wellness-webhook-secret") || "";
  if (!secretsMatch(suppliedSecret, expectedSecret)) {
    return jsonResponse(401, { error: "Unauthorized." });
  }

  const contentLength = Number(request.headers.get("content-length") || 0);
  if (contentLength > 4096) {
    return jsonResponse(413, { error: "Payload is too large." });
  }

  let rawBody: string;
  try {
    rawBody = await request.text();
  } catch (error) {
    console.error("Could not read the appointment status event.", error);
    return jsonResponse(400, { error: "Invalid JSON payload." });
  }
  if (new TextEncoder().encode(rawBody).length > 4096) {
    return jsonResponse(413, { error: "Payload is too large." });
  }

  let payloadValue: unknown;
  try {
    payloadValue = JSON.parse(rawBody);
  } catch {
    return jsonResponse(400, { error: "Invalid JSON payload." });
  }
  if (!isRecord(payloadValue)) {
    return jsonResponse(400, { error: "Invalid appointment status event." });
  }

  const payload = payloadValue as AppointmentStatusPayload;
  const allowedFields = new Set([
    "request_id",
    "patient_email",
    "approval_status",
    "requested_date",
    "requested_time_slot",
    "confirmed_date",
    "confirmed_time_slot",
  ]);
  if (Object.keys(payloadValue).some((field) => !allowedFields.has(field))) {
    return jsonResponse(400, { error: "Unexpected payload fields." });
  }

  const patientEmail = typeof payload.patient_email === "string"
    ? payload.patient_email.trim()
    : "";
  if (!patientEmail) return jsonResponse(200, { ok: "true" });
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(patientEmail)) {
    return jsonResponse(400, { error: "Invalid patient email address." });
  }

  const status = typeof payload.approval_status === "string"
    ? payload.approval_status.trim().toLowerCase()
    : "";
  if (!["scheduled", "confirmed", "rescheduled", "declined", "cancelled"].includes(status)) {
    return jsonResponse(200, { ok: "true" });
  }

  const isDeclined = status === "declined" || status === "cancelled";
  const scheduleDate = isDeclined
    ? formatDate(payload.requested_date)
    : formatDate(payload.confirmed_date ?? payload.requested_date);
  const scheduleTime = isDeclined
    ? formatTime(payload.requested_time_slot)
    : formatTime(payload.confirmed_time_slot ?? payload.requested_time_slot);
  if (!scheduleDate || !scheduleTime) {
    console.error("Appointment status event is missing a valid date or time.");
    return jsonResponse(400, { error: "Appointment schedule is invalid." });
  }

  const resendApiKey = Deno.env.get("RESEND_API_KEY");
  const resendFromEmail = Deno.env.get("RESEND_FROM_EMAIL");
  if (!resendApiKey || !resendFromEmail) {
    console.error("Resend credentials are not fully configured.");
    return jsonResponse(500, { error: "Notification service is not configured." });
  }

  let subject: string;
  let text: string;
  if (status === "scheduled" || status === "confirmed") {
    subject = "Appointment confirmed - Holy Face Center";
    text = [
      "Hello,",
      "",
      `We look forward to seeing you on ${scheduleDate} (${scheduleTime}) at Brothers of Charity – Holy Face Center for Mental Health, Tabiguian, Tabaco City, Albay.`,
      "",
      "If you need to reschedule or have questions, please call us at 0920-691-5015 (Monday–Friday, 8:00 AM–4:00 PM).",
      "",
      "Holy Face Center for Mental Health",
    ].join("\n");
  } else if (status === "rescheduled") {
    subject = "Appointment rescheduled - Holy Face Center";
    text = [
      "Hello,",
      "",
      `Your appointment at Brothers of Charity – Holy Face Center for Mental Health has been rescheduled to ${scheduleDate} (${scheduleTime}).`,
      "",
      "If this new schedule does not work for you, please call us at 0920-691-5015 (Monday–Friday, 8:00 AM–4:00 PM).",
      "",
      "Holy Face Center for Mental Health",
    ].join("\n");
  } else {
    subject = "Appointment request update - Holy Face Center";
    text = [
      "Hello,",
      "",
      `We are unable to accommodate your requested schedule for ${scheduleDate} (${scheduleTime}) at Brothers of Charity – Holy Face Center for Mental Health.`,
      "Please submit a new preferred schedule in the Patient Portal or call us at 0920-691-5015 (Monday–Friday, 8:00 AM–4:00 PM) so we can assist you.",
      "",
      "Holy Face Center for Mental Health",
    ].join("\n");
  }

  try {
    const resendResponse = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${resendApiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: resendFromEmail,
        to: [patientEmail],
        subject,
        text,
      }),
    });
    if (!resendResponse.ok) {
      console.error("Resend returned an unsuccessful response.", resendResponse.status);
      return jsonResponse(502, { error: "Could not send the appointment update." });
    }
  } catch (error) {
    console.error("Resend request failed.", error);
    return jsonResponse(502, { error: "Could not send the appointment update." });
  }

  return jsonResponse(200, { ok: "true" });
});
