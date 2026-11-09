export function showFeedback(text, type) {
  const feedback = document.querySelector("#form-message");
  feedback.textContent = text;
  feedback.className = `form-message ${type}`;
  feedback.hidden = false;
}

export function hideFeedback() {
  const feedback = document.querySelector("#form-message");
  feedback.hidden = true;
  feedback.textContent = "";
  feedback.className = "form-message";
}
