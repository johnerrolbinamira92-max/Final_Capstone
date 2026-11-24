const RETENTION_DAYS = 30;
const LEGACY_STORAGE_KEY = "hfrc-private-entries-v1";
const LEGACY_GUEST_STORAGE_KEY = "hfrc_guest_journal_entries";
const LEGACY_USER_STORAGE_PREFIX = "hfrc_user_journal_";
const STORAGE_PREFIX = "hfrc_journal_entries:";
const GUEST_STORAGE_KEY = `${STORAGE_PREFIX}guest`;

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

function storageKey(userId) {
  return userId ? `${STORAGE_PREFIX}${userId}` : GUEST_STORAGE_KEY;
}

function isBackedUp(entry) {
  return Boolean(entry.cloudSynced || entry.backedUp);
}

function normalizeEntries(values, userId) {
  const cutoff = Date.now() - RETENTION_DAYS * 24 * 60 * 60 * 1000;
  return values
    .filter((entry) =>
      entry &&
      typeof entry.id === "string" &&
      typeof entry.text === "string" &&
      Number.isFinite(entry.createdAt) &&
      entry.createdAt >= cutoff &&
      (userId || !isBackedUp(entry)) &&
      (
        userId
          ? !entry.ownerId || entry.ownerId === userId
          : !entry.ownerId
      )
    )
    .map((entry) => ({
      id: entry.id,
      text: entry.text,
      createdAt: entry.createdAt,
      ...(userId
        ? { cloudSynced: isBackedUp(entry), ownerId: userId }
        : {})
    }));
}

function mergeEntries(existing, incoming) {
  const merged = new Map(existing.map((entry) => [entry.id, entry]));
  incoming.forEach((entry) => {
    const current = merged.get(entry.id);
    if (!current || entry.createdAt >= current.createdAt) {
      merged.set(entry.id, entry);
    }
  });
  return Array.from(merged.values());
}

export function createPrivateEntries({
  historyElement,
  onStorageError,
  onRemove,
  onMilestone
}) {
  let storageUnavailable = false;
  let currentUserId = null;
  let scopeVersion = 0;
  let entries = [];

  function reportStorageError(message, error) {
    console.error(message, error);
    storageUnavailable = true;
    onStorageError("This browser could not safely access your private entries.");
  }

  function readScopedEntries(key, userId) {
    const serialized = localStorage.getItem(key);
    if (serialized === null) return [];
    const saved = JSON.parse(serialized);
    if (!Array.isArray(saved)) {
      throw new TypeError("The saved journal data is not a list.");
    }
    const normalized = normalizeEntries(saved, userId);
    const normalizedSerialized = JSON.stringify(normalized);
    if (!userId && serialized !== normalizedSerialized) {
      localStorage.setItem(key, normalizedSerialized);
    }
    return normalized;
  }

  function migrateLegacyEntries() {
    let serialized;
    try {
      serialized = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (serialized === null) return;

      const saved = JSON.parse(serialized);
      if (!Array.isArray(saved)) {
        throw new TypeError("The legacy journal data is not a list.");
      }

      const partitions = new Map();
      const cutoff = Date.now() - RETENTION_DAYS * 24 * 60 * 60 * 1000;
      saved.forEach((entry) => {
        if (
          !entry ||
          typeof entry.id !== "string" ||
          typeof entry.text !== "string" ||
          !Number.isFinite(entry.createdAt) ||
          entry.createdAt < cutoff
        ) {
          return;
        }

        const ownerId = typeof entry.ownerId === "string" && entry.ownerId
          ? entry.ownerId
          : null;
        const key = storageKey(ownerId);
        const partition = partitions.get(key) || { userId: ownerId, entries: [] };
        partition.entries.push(...normalizeEntries([entry], ownerId));
        partitions.set(key, partition);
      });

      partitions.forEach(({ userId, entries: migrated }, key) => {
        const existing = readScopedEntries(key, userId);
        localStorage.setItem(
          key,
          JSON.stringify(mergeEntries(existing, migrated))
        );
      });
      localStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch (error) {
      reportStorageError("Could not safely separate legacy journal data.", error);
    }
  }

  function migrateScopedEntries() {
    try {
      const migrateKey = (sourceKey, userId) => {
        const serialized = localStorage.getItem(sourceKey);
        if (serialized === null) return;
        const saved = JSON.parse(serialized);
        if (!Array.isArray(saved)) {
          throw new TypeError("The saved journal data is not a list.");
        }
        const destinationKey = storageKey(userId);
        const existing = readScopedEntries(destinationKey, userId);
        const migrated = normalizeEntries(saved, userId);
        localStorage.setItem(
          destinationKey,
          JSON.stringify(mergeEntries(existing, migrated))
        );
        localStorage.removeItem(sourceKey);
      };

      migrateKey(LEGACY_GUEST_STORAGE_KEY, null);
      const legacyUserKeys = [];
      for (let index = 0; index < localStorage.length; index += 1) {
        const key = localStorage.key(index);
        if (key && key.startsWith(LEGACY_USER_STORAGE_PREFIX)) {
          legacyUserKeys.push(key);
        }
      }
      legacyUserKeys.forEach((key) => {
        const userId = key.slice(LEGACY_USER_STORAGE_PREFIX.length);
        if (userId) migrateKey(key, userId);
      });
    } catch (error) {
      reportStorageError("Could not migrate scoped journal data.", error);
    }
  }

  function loadEntries(userId) {
    try {
      return readScopedEntries(storageKey(userId), userId);
    } catch (error) {
      reportStorageError("Could not read private entries from this device.", error);
      return [];
    }
  }

  function persistEntries() {
    try {
      localStorage.setItem(
        storageKey(currentUserId),
        JSON.stringify(entries)
      );
      return true;
    } catch (error) {
      console.error("Could not save private entry to this device.", error);
      storageUnavailable = true;
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
    const scopeAtClick = scopeVersion;
    const entry = entries.find((candidate) => candidate.id === button.dataset.entryId);
    try {
      if (
        entry &&
        currentUserId &&
        entry.cloudSynced &&
        onRemove &&
        !(await onRemove(entry))
      ) return;
    } catch (error) {
      if (scopeAtClick !== scopeVersion) return;
      console.error("Could not remove journal entry.", error);
      onStorageError("This entry could not be removed right now. Please try again.");
      return;
    }
    if (scopeAtClick !== scopeVersion) return;

    const previousEntries = entries;
    entries = entries.filter((candidate) => candidate.id !== button.dataset.entryId);
    if (persistEntries()) {
      render();
    } else {
      entries = previousEntries;
      render();
    }
  });

  migrateLegacyEntries();
  migrateScopedEntries();
  entries = loadEntries(null);

  function setUser(user) {
    const userId = typeof user === "string"
      ? user
      : user && typeof user.id === "string"
        ? user.id
        : null;
    const nextUserId = typeof userId === "string" && userId.trim()
      ? userId
      : null;
    if (currentUserId !== nextUserId) {
      scopeVersion += 1;
      entries = [];
      render();
    }
    currentUserId = nextUserId;
    entries = loadEntries(currentUserId);
    render();
    return entries.length;
  }

  async function sync(client, userId) {
    if (!client || !userId || currentUserId !== userId) {
      throw new Error("Cannot sync journal entries outside the active account.");
    }

    const pendingEntries = entries.filter(
      (entry) => entry.ownerId === userId && !entry.cloudSynced
    );
    if (pendingEntries.length) {
      const { error: saveError } = await client
        .from("patient_journal_entries")
        .upsert(pendingEntries.map((entry) => ({
          user_id: userId,
          client_entry_id: entry.id,
          content: entry.text,
          created_at: new Date(entry.createdAt).toISOString()
        })), { onConflict: "user_id,client_entry_id" });
      if (saveError) throw saveError;
    }

    const { data, error } = await client
      .from("patient_journal_entries")
      .select("user_id, client_entry_id, content, created_at")
      .eq("user_id", userId)
      .order("created_at", { ascending: false });
    if (error) throw error;
    if (currentUserId !== userId) return 0;

    const syncedEntries = new Map(
      entries
        .filter((entry) => entry.ownerId === userId && !entry.cloudSynced)
        .map((entry) => [entry.id, entry])
    );
    (data || [])
      .filter((entry) => entry.user_id === userId)
      .forEach((entry) => {
        syncedEntries.set(entry.client_entry_id, {
          id: entry.client_entry_id,
          text: entry.content,
          createdAt: new Date(entry.created_at).getTime(),
          cloudSynced: true,
          ownerId: userId
        });
      });

    entries = Array.from(syncedEntries.values());
    if (!persistEntries()) {
      throw new Error("Entries are backed up, but this browser could not update the local copy.");
    }
    return entries.length;
  }

  async function importGuestEntries(client, user) {
    const userId = typeof user === "string" ? user : user?.id;
    if (!userId || currentUserId !== userId) {
      throw new Error("Cannot import guest entries outside the active account.");
    }

    const guestEntries = loadEntries(null);
    const previousEntries = entries;
    entries = mergeEntries(
      entries,
      normalizeEntries(guestEntries, userId).map((entry) => ({
        ...entry,
        cloudSynced: false,
        ownerId: userId
      }))
    );
    if (!persistEntries()) {
      entries = previousEntries;
      throw new Error("Guest entries could not be saved to this account on this device.");
    }

    await sync(client, userId);
    if (currentUserId !== userId) {
      throw new Error("The active account changed before guest entries finished importing.");
    }
    return guestEntries.length;
  }

  return {
    get storageUnavailable() {
      return storageUnavailable;
    },
    setUser,
    getGuestEntries() {
      return loadEntries(null);
    },
    clearGuestEntries() {
      try {
        localStorage.removeItem(GUEST_STORAGE_KEY);
      } catch (error) {
        reportStorageError("Could not clear guest journal entries.", error);
        throw error;
      }
      if (!currentUserId) {
        entries = [];
        render();
      }
    },
    clearUserEntries(userId) {
      if (!userId) throw new Error("An account ID is required to clear journal entries.");
      if (currentUserId === userId) {
        entries = [];
        render();
      }
      try {
        localStorage.removeItem(storageKey(userId));
      } catch (error) {
        reportStorageError("Could not clear this account's local journal copy.", error);
        throw error;
      }
    },
    importGuestEntries,
    clearLegacyStorage() {
      try {
        localStorage.removeItem(LEGACY_STORAGE_KEY);
      } catch (error) {
        reportStorageError("Could not remove legacy journal data.", error);
      }
    },
    clearDisplay() {
      historyElement.replaceChildren();
    },
    clearForAccountChange() {
      scopeVersion += 1;
      entries = [];
      historyElement.replaceChildren();
    },
    save(text) {
      const entry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        text,
        createdAt: Date.now(),
        ...(currentUserId ? { ownerId: currentUserId } : {})
      };
      entries.push(entry);
      if (persistEntries()) {
        if (entries.length > 0 && entries.length % 5 === 0 && onMilestone) {
          onMilestone(entries.length, currentUserId);
        }
        return true;
      }
      entries = entries.filter((candidate) => candidate.id !== entry.id);
      return false;
    },
    sync,
    render
  };
}
