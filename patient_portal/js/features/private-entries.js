const RETENTION_DAYS = 30;
const STORAGE_KEY = "hfrc-private-entries-v1";

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

export function createPrivateEntries({ historyElement, onStorageError }) {
  let storageUnavailable = false;
  let entries = [];

  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    if (Array.isArray(saved)) {
      const cutoff = Date.now() - RETENTION_DAYS * 24 * 60 * 60 * 1000;
      entries = saved.filter((entry) =>
        entry && typeof entry.text === "string" &&
        Number.isFinite(entry.createdAt) && entry.createdAt >= cutoff
      );
      localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    }
  } catch (error) {
    console.error("Could not read private entries from this device.", error);
    storageUnavailable = true;
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
      return true;
    } catch (error) {
      console.error("Could not save private entry to this device.", error);
      onStorageError("This browser could not save your entry. Check available device storage and try again.");
      return false;
    }
  }

  function render() {
    if (!entries.length) {
      historyElement.innerHTML = '<div class="empty-history"><span aria-hidden="true">♙</span><strong>No active private entries on this device.</strong><p>Private entries you save will appear here for up to 30 days.</p></div>';
      return;
    }
    historyElement.innerHTML = entries
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

  historyElement.addEventListener("click", (event) => {
    const button = event.target.closest("[data-entry-id]");
    if (!button) return;
    entries = entries.filter((entry) => entry.id !== button.dataset.entryId);
    if (save()) render();
  });

  return {
    get storageUnavailable() {
      return storageUnavailable;
    },
    save(text) {
      entries.push({
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        text,
        createdAt: Date.now()
      });
      return save();
    },
    render
  };
}
