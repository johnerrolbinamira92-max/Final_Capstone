import { sendHelpRequest } from "./features/callback-request.js";
import { initCallbackSchedule } from "./features/callback-schedule.js";
import { createPrivateEntries } from "./features/private-entries.js";
import { initTheme } from "./features/theme.js";
import { hideFeedback, showFeedback } from "./ui/feedback.js";

const form = document.querySelector("#entry-form");
const messageField = document.querySelector("#message");
const countLabel = document.querySelector("#character-count");
const submitButton = document.querySelector("#submit-button");

const privateEntries = createPrivateEntries({
  historyElement: document.querySelector("#entry-history"),
  onStorageError: (message) => showFeedback(message, "error")
});
const callbackSchedule = initCallbackSchedule({
  onSelection: hideFeedback
});

function setFlow(value) {
  const isHelp = value === "help";
  document.querySelector("#callback-panel").hidden = !isHelp;
  document.querySelector("#private-note-panel").hidden = isHelp;
  submitButton.innerHTML = isHelp
    ? 'Send my help request <span aria-hidden="true">›</span>'
    : 'Store my private entry <span aria-hidden="true">›</span>';
  submitButton.disabled = false;
  submitButton.classList.toggle("private-submit", !isHelp);
  hideFeedback();
}

document.querySelectorAll('input[name="next-step"]').forEach((input) => {
  input.addEventListener("change", () => setFlow(input.value));
});

messageField.addEventListener("input", () => {
  countLabel.textContent = `${messageField.value.length.toLocaleString()} / 10,000`;
  hideFeedback();
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
    await sendHelpRequest({
      form,
      messageField,
      showFeedback,
      hideFeedback,
      onSuccess: () => {
        form.reset();
        callbackSchedule.reset();
        setFlow("help");
        countLabel.textContent = "0 / 10,000";
      }
    });
    return;
  }

  if (!privateEntries.save(text)) return;
  privateEntries.render();
  form.reset();
  form.querySelector('input[name="next-step"][value="private"]').checked = true;
  countLabel.textContent = "0 / 10,000";
  setFlow("private");
  showFeedback("Your private entry was saved on this device only. It will be removed from this list after 30 days.", "success");
});

initTheme();
setFlow(form.querySelector('input[name="next-step"]:checked').value);
callbackSchedule.render();
privateEntries.render();
if (privateEntries.storageUnavailable) {
  showFeedback("This browser could not access device storage. Private entries cannot be saved here.", "error");
}
