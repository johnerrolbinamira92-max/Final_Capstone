const MAX_MESSAGES = 8;
const MAX_USER_MESSAGE_LENGTH = 500;
const STARTER_PROMPTS = [
  "How do I request a callback?",
  "Clinic hours & contact",
  "Help me calm down (grounding)"
];

const messages = [];
const config = window.PATIENT_PORTAL_CONFIG || {};

document.body.insertAdjacentHTML("beforeend", `
  <div class="care-chatbot-widget">
    <section
      class="care-chatbot-panel"
      id="care-chatbot-panel"
      role="dialog"
      aria-modal="false"
      aria-labelledby="care-chatbot-heading"
      hidden
    >
      <header class="care-chatbot-header">
        <div>
          <h2 class="care-chatbot-heading" id="care-chatbot-heading">Holy Face Care Assistant</h2>
          <p class="care-chatbot-subheading">A gentle place to ask for support</p>
        </div>
        <button class="care-chatbot-close" type="button" aria-label="Close Care Assistant">×</button>
      </header>
      <p class="care-chatbot-privacy">Session-only chat • Not saved to your journal or visible to staff</p>
      <div class="care-chatbot-starters" role="group" aria-label="Suggested questions">
        ${STARTER_PROMPTS.map((prompt) =>
          `<button class="care-chatbot-chip" type="button">${prompt}</button>`
        ).join("")}
      </div>
      <div
        class="care-chatbot-messages"
        id="care-chatbot-messages"
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label="Care Assistant conversation"
      ></div>
      <form class="care-chatbot-composer">
        <label class="sr-only" for="care-chatbot-input">Your message</label>
        <input
          class="care-chatbot-input"
          id="care-chatbot-input"
          name="message"
          type="text"
          maxlength="500"
          autocomplete="off"
          placeholder="Type a message..."
          required
        >
        <button class="care-chatbot-send" type="submit">Send</button>
      </form>
    </section>
    <button
      class="care-chatbot-toggle"
      type="button"
      aria-controls="care-chatbot-panel"
      aria-expanded="false"
    >
      <span class="care-chatbot-toggle-icon" aria-hidden="true">♡</span>
      <span>Care Assistant</span>
    </button>
  </div>
`);

const panel = document.querySelector("#care-chatbot-panel");
const toggle = document.querySelector(".care-chatbot-toggle");
const closeButton = document.querySelector(".care-chatbot-close");
const messageList = document.querySelector("#care-chatbot-messages");
const input = document.querySelector("#care-chatbot-input");
const sendButton = document.querySelector(".care-chatbot-send");
const starterButtons = [...document.querySelectorAll(".care-chatbot-chip")];
const form = document.querySelector(".care-chatbot-composer");

function renderMessage(role, text) {
  const message = document.createElement("div");
  message.className = "care-chatbot-message";
  message.dataset.role = role;
  message.textContent = text;
  messageList.append(message);
  messageList.scrollTop = messageList.scrollHeight;
  return message;
}

function trimConversation() {
  if (messages.length > MAX_MESSAGES) {
    messages.splice(0, messages.length - MAX_MESSAGES);
  }
}

async function sendMessage(value) {
  const text = value.trim();
  if (!text || text.length > MAX_USER_MESSAGE_LENGTH || sendButton.disabled) return;

  messages.push({ role: "user", text });
  trimConversation();
  renderMessage("user", text);
  input.value = "";
  sendButton.disabled = true;
  starterButtons.forEach((button) => {
    button.disabled = true;
  });
  input.disabled = true;
  const thinkingMessage = renderMessage("status", "One moment...");

  try {
    if (!config.supabaseUrl || !config.supabaseAnonKey) {
      throw new Error("The Patient Portal Supabase configuration is unavailable.");
    }

    const response = await fetch(
      `${config.supabaseUrl.replace(/\/$/, "")}/functions/v1/patient-chatbot`,
      {
        method: "POST",
        headers: {
          apikey: config.supabaseAnonKey,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ messages: messages.slice(-MAX_MESSAGES) })
      }
    );
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(result?.error || `Care Assistant request failed (${response.status}).`);
    }
    if (typeof result?.reply !== "string" || !result.reply.trim()) {
      throw new Error("The Care Assistant returned an empty reply.");
    }

    const reply = result.reply.trim();
    messages.push({ role: "assistant", text: reply });
    trimConversation();
    thinkingMessage.remove();
    renderMessage("assistant", reply);
  } catch (error) {
    console.error("Care Assistant request failed.", error);
    thinkingMessage.remove();
    renderMessage(
      "error",
      "I couldn’t connect just now. Please try again, or call the center at 0920-691-5015 on weekdays, 8:00 AM–5:00 PM."
    );
  } finally {
    sendButton.disabled = false;
    starterButtons.forEach((button) => {
      button.disabled = false;
    });
    input.disabled = false;
    input.focus();
  }
}

function setOpen(open) {
  panel.hidden = !open;
  toggle.setAttribute("aria-expanded", String(open));
  if (open) input.focus();
  else toggle.focus();
}

toggle.addEventListener("click", () => {
  setOpen(panel.hidden);
});

closeButton.addEventListener("click", () => {
  setOpen(false);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !panel.hidden) {
    setOpen(false);
  }
});

starterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    sendMessage(button.textContent || "");
  });
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});
