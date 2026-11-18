type NotificationPayload = {
  user_id?: unknown;
  patient_email?: unknown;
  entry_count?: unknown;
};

type GeminiResponse = {
  candidates?: Array<{
    content?: {
      parts?: Array<{ text?: string; thought?: boolean }>;
    };
  }>;
};

const htmlEscapes: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

function jsonResponse(status: number, body: Record<string, string>) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function secretsMatch(candidate: string, expected: string) {
  let difference = candidate.length ^ expected.length;
  const length = Math.max(candidate.length, expected.length);
  for (let index = 0; index < length; index += 1) {
    difference |= (candidate.charCodeAt(index) || 0) ^ (expected.charCodeAt(index) || 0);
  }
  return difference === 0;
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => htmlEscapes[character] || character);
}

function isNotificationPayload(value: unknown): value is NotificationPayload {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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

  const contentLength = Number(request.headers.get("content-length") || 0);
  if (contentLength > 4096) {
    return jsonResponse(413, { error: "Payload is too large." });
  }

  const suppliedSecret = request.headers.get("x-wellness-webhook-secret") || "";
  if (!secretsMatch(suppliedSecret, expectedSecret)) {
    return jsonResponse(401, { error: "Unauthorized." });
  }

  let payloadValue: unknown;
  try {
    payloadValue = await request.json();
  } catch {
    return jsonResponse(400, { error: "Invalid JSON payload." });
  }
  if (!isNotificationPayload(payloadValue)) {
    return jsonResponse(400, { error: "Invalid wellness check-in event." });
  }
  const payload = payloadValue;
  const allowedFields = new Set(["user_id", "patient_email", "entry_count"]);
  if (Object.keys(payload).some((field) => !allowedFields.has(field))) {
    return jsonResponse(400, { error: "Unexpected payload fields." });
  }

  const userId = typeof payload.user_id === "string" ? payload.user_id : "";
  const patientEmail = typeof payload.patient_email === "string"
    ? payload.patient_email.trim()
    : "";
  const entryCount = payload.entry_count;
  const isValidEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(patientEmail);
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(userId) ||
    !isValidEmail ||
    typeof entryCount !== "number" ||
    !Number.isSafeInteger(entryCount) ||
    entryCount <= 0 ||
    entryCount % 5 !== 0
  ) {
    return jsonResponse(400, { error: "Invalid wellness check-in event." });
  }

  const geminiApiKey = Deno.env.get("GEMINI_API_KEY");
  const resendApiKey = Deno.env.get("RESEND_API_KEY");
  const resendFromEmail = Deno.env.get("RESEND_FROM_EMAIL");
  if (!geminiApiKey || !resendApiKey || !resendFromEmail) {
    console.error("Gemini or Resend credentials are not fully configured.");
    return jsonResponse(500, { error: "Notification service is not configured." });
  }

  let wellnessMessage: string;
  try {
    const geminiResponse = await fetch(
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": geminiApiKey,
        },
        body: JSON.stringify({
          system_instruction: {
            parts: [{
              text: [
                "Write a brief, warm, non-clinical wellness check-in from Holy Face Center for Mental Health.",
                "Acknowledge the person's consistency in making time to journal, without assuming how they feel.",
                "Do not diagnose, give treatment advice, or claim to know anything about their journal entries.",
                "Use one or two short sentences and gentle, everyday language.",
              ].join(" "),
            }],
          },
          contents: [{
            parts: [{
              text: `This person has saved ${entryCount} private journal entries. Do not mention this count.`,
            }],
          }],
          generationConfig: { temperature: 0.6, maxOutputTokens: 120 },
        }),
      },
    );
    if (!geminiResponse.ok) {
      console.error("Gemini returned an unsuccessful response.", geminiResponse.status);
      return jsonResponse(502, { error: "Could not prepare the wellness check-in." });
    }

    const result = await geminiResponse.json() as GeminiResponse;
    wellnessMessage = result.candidates?.[0]?.content?.parts
      ?.filter((part) => !part.thought)
      ?.map((part) => part.text || "")
      .join("")
      .trim() || "";
    if (!wellnessMessage) {
      console.error("Gemini returned an empty wellness message.");
      return jsonResponse(502, { error: "Could not prepare the wellness check-in." });
    }
  } catch (error) {
    console.error("Gemini request failed.", error);
    return jsonResponse(502, { error: "Could not prepare the wellness check-in." });
  }

  const supportReminder =
    "Compassionate support and confidential callbacks are available anytime at 0920-691-5015.";
  const safeMessage = escapeHtml(wellnessMessage).replace(/\r?\n/g, "<br>");
  const emailText = `Hello,\n\n${wellnessMessage}\n\n${supportReminder}\n\nHoly Face Center for Mental Health`;
  const emailHtml = [
    "<p>Hello,</p>",
    `<p>${safeMessage}</p>`,
    `<p>${escapeHtml(supportReminder)}</p>`,
    "<p>Holy Face Center for Mental Health</p>",
  ].join("");

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
        subject: "A gentle check-in from Holy Face Center",
        text: emailText,
        html: emailHtml,
      }),
    });
    if (!resendResponse.ok) {
      console.error("Resend returned an unsuccessful response.", resendResponse.status);
      return jsonResponse(502, { error: "Could not send the wellness check-in." });
    }
  } catch (error) {
    console.error("Resend request failed.", error);
    return jsonResponse(502, { error: "Could not send the wellness check-in." });
  }

  return jsonResponse(200, { ok: "true" });
});
