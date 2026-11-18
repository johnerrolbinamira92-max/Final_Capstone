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

export function createPrivateEntries({ historyElement, onStorageError, onRemove }) {
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
      historyElement.innerHTML = '<div class="empty-history"><span aria-hidden="true">♙</span><strong>No active private entries.</strong><p>Private entries you save or back up will appear here.</p></div>';
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
          <div class="entry-card-top"><span class="entry-badge">${entry.cloudSynced ? "Backed up" : "Private release"}</span><span>${entry.cloudSynced ? "Stored permanently" : `${remaining} day${remaining === 1 ? "" : "s"} left`}</span></div>
          <p class="entry-copy">${escapeHtml(entry.text)}</p>
          <div class="entry-card-bottom"><span>${escapeHtml(created)}<br>${entry.cloudSynced ? "Backed up to your account" : "Saved on this device"}</span><button type="button" class="remove-entry" data-entry-id="${escapeHtml(entry.id)}">Remove</button></div>
        </article>`;
      }).join("");
  }

  historyElement.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-entry-id]");
    if (!button) return;
    const entry = entries.find((candidate) => candidate.id === button.dataset.entryId);
    try {
      if (entry && onRemove && !(await onRemove(entry))) return;
    } catch (error) {
      console.error("Could not remove journal entry.", error);
      onStorageError("This entry could not be removed right now. Please try again.");
      return;
    }
    entries = entries.filter((candidate) => candidate.id !== button.dataset.entryId);
    if (save()) render();
  });

  return {
    get storageUnavailable() {
      return storageUnavailable;
    },
    save(text, ownerId) {
      const entry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        text,
        createdAt: Date.now(),
        ...(ownerId ? { ownerId } : {})
      };
      entries.push(entry);
      return save();
    },
    async sync(client, userId) {
      entries = entries.filter((entry) => !entry.ownerId || entry.ownerId === userId);
      if (entries.length) {
        const { error: saveError } = await client
          .from("patient_journal_entries")
          .upsert(entries.map((entry) => ({
            user_id: userId,
            client_entry_id: entry.id,
            content: entry.text,
            created_at: new Date(entry.createdAt).toISOString()
          })), { onConflict: "user_id,client_entry_id" });
        if (saveError) throw saveError;
      }

      const { data, error } = await client
        .from("patient_journal_entries")
        .select("client_entry_id, content, created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false });
      if (error) throw error;

      const merged = new Map(entries.map((entry) => [entry.id, entry]));
      data.forEach((entry) => {
        merged.set(entry.client_entry_id, {
          id: entry.client_entry_id,
          text: entry.content,
          createdAt: new Date(entry.created_at).getTime(),
          cloudSynced: true,
          ownerId: userId
        });
      });
      entries = Array.from(merged.values()).map((entry) => ({
        ...entry,
        cloudSynced: true,
        ownerId: userId
      }));
      if (!save()) throw new Error("Entries are backed up, but this browser could not update the local copy.");
      return entries.length;
    },
    render
  };
}
