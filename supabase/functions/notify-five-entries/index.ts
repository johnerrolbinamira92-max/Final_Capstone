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

const checkInStyles = [
  {
    subject: "Taking a quiet moment to check in on you",
    instruction: [
      "Acknowledge the person's intention and care in taking time to pause and reflect, without assuming how they feel or mentioning entry counts.",
      "Reassure them that whenever things feel heavy—or even if they just want someone to listen—our team at Brothers of Charity - Holy Face Center for Mental Health is here without judgment.",
      "Keep it to two short, comforting sentences without diagnosing or implying anyone read their journal.",
    ].join(" "),
  },
  {
    subject: "A gentle check-in from Holy Face Center",
    instruction: [
      "Write a brief, calm, minimalist check-in acknowledging that checking in with oneself regularly is a meaningful step and expressing that we are glad they have a private space here whenever needed, with zero pressure to reply.",
      "Keep it to two brief sentences without diagnosing or mentioning entry counts.",
    ].join(" "),
  },
  {
    subject: "We’re here whenever you’re ready to talk",
    instruction: [
      "Write a gentle outreach check-in acknowledging that building a steady habit of self-reflection shows real strength, reminding them they never have to carry everything alone, and inviting them to connect with our care team or request a callback at their own pace.",
      "Keep it to two supportive sentences without diagnosing or mentioning entry counts.",
    ].join(" "),
  },
];

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

  const checkInStyle = checkInStyles[Math.floor(Math.random() * checkInStyles.length)];
  let wellnessMessage: string;
  try {
    const geminiResponse = await fetch(
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": geminiApiKey,
        },
        body: JSON.stringify({
          system_instruction: {
            parts: [{ text: checkInStyle.instruction }],
          },
          contents: [{ parts: [{ text: "Write the check-in message." }] }],
          generationConfig: { temperature: 0.6, maxOutputTokens: 180 },
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
    "Compassionate support and confidential callbacks are available at 0920-691-5015 (Monday–Friday, 8:00 AM–4:00 PM) or anytime through the Patient Portal. For 24/7 urgent support, you may also call the National Center for Mental Health Crisis Hotline at 1553 (landline) or 0919-057-1553 (Smart/TNT) / 0917-899-8727 (Globe/TM).";
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
        subject: checkInStyle.subject,
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
