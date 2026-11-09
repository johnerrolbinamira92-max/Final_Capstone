export function initTheme() {
  const themeToggle = document.querySelector("#theme-toggle");
  themeToggle.addEventListener("click", (event) => {
    const light = document.body.classList.toggle("light-theme");
    event.currentTarget.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
  });
  themeToggle.setAttribute("aria-label", "Switch to light theme");
}
