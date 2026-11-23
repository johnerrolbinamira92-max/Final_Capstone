import { sendHelpRequest } from "./features/callback-request.js?v=2";
import { initCallbackSchedule } from "./features/callback-schedule.js?v=2";
import { createPrivateEntries } from "./features/private-entries.js?v=3";
import { hideFeedback, showFeedback } from "./ui/feedback.js";

const GUEST_REQUEST_TOKENS_KEY = "hfrc_guest_request_tokens";
const GUEST_REQUEST_SEEN_KEY = "hfrc_guest_request_seen";
const GUEST_WELLNESS_ITEMS_KEY = "hfrc_guest_wellness_checkins";
const GUEST_WELLNESS_MESSAGE = "You've checked in 5 times in your Vent-Out Space. Taking time to reflect matters—if you'd ever like someone to talk to, our Care Assistant or callback team at Holy Face Center is here for you.";

const form = document.querySelector("#entry-form");
const messageField = document.querySelector("#message");
const countLabel = document.querySelector("#character-count");
const submitButton = document.querySelector("#submit-button");
const viewTabs = Array.from(document.querySelectorAll('[role="tab"]'));
const authDialog = document.querySelector("#auth-dialog");
const authForm = document.querySelector("#auth-form");
const authError = document.querySelector("#auth-error");
const authSubmit = document.querySelector("#auth-submit");
const authPasswordInput = document.querySelector("#auth-input-password");
const authPasswordToggle = document.querySelector("#auth-password-toggle");
const authWellnessConsent = document.querySelector("#auth-wellness-consent");
const authWellnessOptIn = document.querySelector("#auth-wellness-opt-in");
const wellnessEmailSetting = document.querySelector("#wellness-email-setting");
const wellnessEmailOptIn = document.querySelector("#wellness-email-opt-in");
const wellnessEmailStatus = document.querySelector("#wellness-email-status");
const authModeTabs = [
  { element: document.querySelector("#auth-signin-tab"), mode: "signin" },
  { element: document.querySelector("#auth-signup-tab"), mode: "signup" }
];
const authOpenButton = document.querySelector("#auth-open-button");
const authAccount = document.querySelector("#auth-account");
const authEmail = document.querySelector("#auth-email");
const accountMenu = document.querySelector(".account-menu");
const accountButton = document.querySelector("#account-menu-button");
const accountPopover = document.querySelector("#account-popover");
const notificationMenu = document.querySelector(".notification-menu");
const notificationButton = document.querySelector("#notification-button");
const notificationBadge = document.querySelector("#notification-badge");
const notificationPopover = document.querySelector("#notification-popover");
const notificationLatest = document.querySelector("#notification-latest");
const notificationHistory = document.querySelector("#notification-history");
const notificationRequestCount = document.querySelector("#notification-request-count");
const guestWellnessBanner = document.querySelector("#guest-wellness-banner");
const guestWellnessMessage = document.querySelector("#guest-wellness-message");
const guestWellnessAssistant = document.querySelector("#guest-wellness-assistant");
const guestWellnessCallback = document.querySelector("#guest-wellness-callback");
const guestWellnessDismiss = document.querySelector("#guest-wellness-dismiss");
const guestImportBanner = document.querySelector("#guest-import-banner");
const guestImportCopy = document.querySelector("#guest-import-copy");
const guestImportButton = document.querySelector("#guest-import-button");
const guestImportDismiss = document.querySelector("#guest-import-dismiss");
const guestImportStatus = document.querySelector("#guest-import-status");
const historySigninBanner = document.querySelector("#history-signin-banner");
const textareaGuestPrompt = document.querySelector("#textarea-guest-prompt");
const privateEntrySigninHelper = document.querySelector("#private-entry-signin-helper");
const entryToast = document.querySelector("#entry-toast");
const config = window.PATIENT_PORTAL_CONFIG || {};
let supabase = null;
let authUnavailable = false;
let currentSession = null;
let authReady = !config.supabaseUrl || !config.supabaseAnonKey;
let authMode = "signin";
let toastTimeout;
let requestPollingTimer = null;
let requestLoadSequence = 0;
let requestRows = [];
let seenRequestStates = new Map();
let guestWellnessItems = [];
let guestImportDismissed = false;
let requestHistoryLoaded = false;
let requestHistoryError = false;

const privateEntries = createPrivateEntries({
  historyElement: document.querySelector("#entry-history"),
  onStorageError: (message) => showFeedback(message, "error"),
  onGuestMilestone: handleGuestWellnessMilestone,
  onRemove: async (entry) => {
    if (!currentSession) return true;
    if (!entry.cloudSynced) return true;
    const userId = entry.ownerId;
    if (
      !supabase ||
      !userId ||
      !currentSession ||
      currentSession.user.id !== userId
    ) {
      return false;
    }
    const { error } = await supabase
      .from("patient_journal_entries")
      .delete()
      .eq("user_id", userId)
      .eq("client_entry_id", entry.id);
    if (error) {
      console.error("Could not remove backed-up journal entry.", error);
      showFeedback("This entry could not be removed from your account. Please try again.", "error");
      return false;
    }
    return true;
  }
});
const callbackSchedule = initCallbackSchedule({
  onSelection: hideFeedback
});

async function recordPortalEngagement(actionType) {
  if (
    !config.supabaseUrl ||
    config.supabaseUrl.includes("YOUR-PROJECT") ||
    !config.supabaseAnonKey ||
    config.supabaseAnonKey.includes("YOUR_SUPABASE")
  ) {
    console.warn(
      "Portal engagement could not be recorded because Supabase is not configured."
    );
    return;
  }

  try {
    if (supabase) {
      const { error } = await supabase.rpc(
        "increment_portal_engagement",
        { action_type: actionType }
      );
      if (error) throw error;
      return;
    }

    const accessToken = currentSession
      ? currentSession.access_token
      : config.supabaseAnonKey;
    const apiUrl = config.supabaseUrl.replace(/\/$/, "");
    const response = await fetch(
      `${apiUrl}/rest/v1/rpc/increment_portal_engagement`,
      {
        method: "POST",
        headers: {
          apikey: config.supabaseAnonKey,
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ action_type: actionType })
      }
    );
    if (!response.ok) {
      const details = await response.text();
      throw new Error(
        `Supabase rejected the portal engagement count (${response.status}): ${details}`
      );
    }
  } catch (error) {
    console.error("Could not record completed portal engagement.", error);
  }
}

function activateView(tab, moveFocus = false) {
  viewTabs.forEach((candidate) => {
    const isActive = candidate === tab;
    candidate.setAttribute("aria-selected", String(isActive));
    candidate.tabIndex = isActive ? 0 : -1;
    document.getElementById(
      candidate.getAttribute("aria-controls")
    ).hidden = !isActive;
  });
  if (tab.getAttribute("aria-controls") === "history") {
    if (authReady) {
      privateEntries.setUser(currentSession ? currentSession.user : null);
    } else {
      privateEntries.clearDisplay();
    }
  }
  if (moveFocus) tab.focus();
}

function openAuthDialog() {
  if (!authDialog.open) authDialog.showModal();
  authError.hidden = !authUnavailable;
  authError.textContent = authUnavailable ? "Sign-in is temporarily unavailable. You can continue using the portal as a guest." : "";
  document.querySelector("#auth-input-email").focus();
}

function setAuthMode(mode) {
  authMode = mode;
  const isSignUp = mode === "signup";
  document.querySelector("#auth-title").textContent = isSignUp ? "Create Patient Account" : "Patient Portal Sign In";
  document.querySelector("#auth-intro").textContent = isSignUp
    ? "Create an account with your email to permanently save private entries and view appointment confirmations."
    : "Sign in with your email to permanently save private entries and view appointment confirmations.";
  authSubmit.textContent = isSignUp ? "Create Account" : "Sign In to Portal";
  authPasswordInput.autocomplete = isSignUp ? "new-password" : "current-password";
  authWellnessConsent.hidden = !isSignUp;
  authPasswordInput.type = "password";
  authPasswordInput.value = "";
  authPasswordToggle.setAttribute("aria-label", "Show password");
  authPasswordToggle.setAttribute("aria-pressed", "false");
  authModeTabs.forEach(({ element, mode: tabMode }) => {
    const isSelected = tabMode === mode;
    element.setAttribute("aria-pressed", String(isSelected));
  });
}

function formatRequestDate(value) {
  if (!value) return "Date not set";
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function formatRequestTime(value) {
  if (!value) return "Time not set";
  const [hours, minutes] = value.slice(0, 5).split(":").map(Number);
  if (!Number.isInteger(hours) || !Number.isInteger(minutes)) return value;
  const time = new Date(2000, 0, 1, hours, minutes);
  return time.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function requestSignature(row) {
  return [
    row.approval_status || "Pending",
    row.updated_at || row.created_at || "",
    row.requested_date || "",
    row.requested_time_slot || "",
    row.confirmed_date || "",
    row.confirmed_time || ""
  ].join("|");
}

function requestHasUnreadUpdate(row) {
  const signature = requestSignature(row);
  const seenSignature = seenRequestStates.get(row.request_id);
  if (seenSignature !== undefined) return seenSignature !== signature;
  if (row.guest) return true;
  if ((row.approval_status || "Pending") === "Pending" || !row.updated_at || !row.created_at) return false;
  return new Date(row.updated_at).getTime() > new Date(row.created_at).getTime();
}

function updateNotificationBadge() {
  const unreadRequests = requestRows.filter(requestHasUnreadUpdate).length;
  const unreadWellness = currentSession
    ? 0
    : guestWellnessItems.filter((item) =>
      seenRequestStates.get(`wellness:${item.id}`) !== item.created_at
    ).length;
  const unreadCount = unreadRequests + unreadWellness;
  notificationBadge.hidden = unreadCount === 0;
  notificationBadge.textContent = unreadCount > 9 ? "9+" : String(unreadCount);
  notificationButton.setAttribute(
    "aria-label",
    unreadCount ? `Request notifications, ${unreadCount} unread updates` : "Request notifications"
  );
}

function notificationTimestampValue(item) {
  return item.type === "wellness"
    ? item.data.created_at
    : item.data.updated_at || item.data.created_at;
}

function notificationTimestamp(item) {
  const timestamp = Date.parse(notificationTimestampValue(item) || "");
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function formatNotificationTimestamp(item) {
  const timestamp = Date.parse(notificationTimestampValue(item) || "");
  return Number.isFinite(timestamp)
    ? new Date(timestamp).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    })
    : "Time unavailable";
}

function renderNotificationItem(item) {
  const notice = document.createElement("article");
  notice.className = "request-history-item";

  if (item.type === "wellness") {
    notice.classList.add("notification-wellness-item");
    const header = document.createElement("div");
    header.className = "request-history-item-header";
    const heading = document.createElement("strong");
    heading.textContent = "Vent-Out Space check-in";
    const status = document.createElement("span");
    status.className = "request-status-badge";
    status.textContent = "Reflection";
    header.append(heading, status);
    const copy = document.createElement("p");
    copy.className = "notification-wellness-copy";
    copy.textContent = GUEST_WELLNESS_MESSAGE;
    const date = document.createElement("p");
    date.textContent = formatNotificationTimestamp(item);
    notice.append(header, copy, date);
    notificationHistory.append(notice);
    return;
  }

  const row = item.data;
  const header = document.createElement("div");
  header.className = "request-history-item-header";
  const requestedDate = document.createElement("strong");
  requestedDate.textContent = formatRequestDate(row.requested_date);
  const status = document.createElement("span");
  status.className = `request-status-badge status-${(row.approval_status || "Pending").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  status.textContent = row.approval_status || "Pending";
  header.append(requestedDate, status);

  const preferredTime = document.createElement("p");
  preferredTime.textContent = `Preferred time: ${formatRequestTime(row.requested_time_slot)}`;
  notice.append(header, preferredTime);
  if (["Scheduled", "Confirmed", "Rescheduled"].includes(row.approval_status)) {
    const confirmedSchedule = document.createElement("p");
    confirmedSchedule.className = "confirmed-schedule";
    confirmedSchedule.textContent = `Confirmed schedule: ${formatRequestDate(row.confirmed_date || row.requested_date)} · ${formatRequestTime(row.confirmed_time || row.requested_time_slot)}`;
    notice.append(confirmedSchedule);
  }
  notificationHistory.append(notice);
}

function renderRequestHistory(rows) {
  notificationLatest.replaceChildren();
  notificationHistory.replaceChildren();
  const items = rows.map((row) => ({ type: "request", data: row }));
  if (!currentSession) {
    guestWellnessItems.forEach((item) => {
      items.push({ type: "wellness", data: item });
    });
  }
  items.sort((first, second) => {
    const difference = notificationTimestamp(second) - notificationTimestamp(first);
    return difference || String(notificationTimestampValue(second) || "").localeCompare(
      String(notificationTimestampValue(first) || "")
    );
  });
  notificationRequestCount.textContent = `${items.length} ${items.length === 1 ? "update" : "updates"}`;

  if (!requestHistoryLoaded) {
    const heading = document.createElement("h2");
    heading.textContent = "Your requests";
    const message = document.createElement("p");
    message.className = "notification-empty";
    message.textContent = "Loading your requests…";
    notificationHistory.append(message);
    if (!items.length) notificationLatest.append(heading);
  } else if (!items.length) {
    const heading = document.createElement("h2");
    heading.textContent = "Your requests";
    const message = document.createElement("p");
    message.className = `notification-empty${requestHistoryError ? " notification-error" : ""}`;
    message.textContent = requestHistoryError
      ? "Request history couldn’t be loaded. Please try again later."
      : currentSession
        ? "You haven’t submitted any callback requests yet."
        : "No appointment updates yet.";
    notificationLatest.append(heading);
    notificationHistory.append(message);
    return;
  }

  if (items.length) {
    const latest = items[0];
    const latestHeading = document.createElement("p");
    latestHeading.className = "notification-eyebrow";
    latestHeading.textContent = "Latest update";
    const latestStatus = document.createElement("p");
    latestStatus.className = "notification-latest-status";
    const latestDetails = document.createElement("p");
    latestDetails.className = "notification-latest-details";

    if (latest.type === "wellness") {
      latestStatus.textContent = `${formatNotificationTimestamp(latest)} — Vent-Out Space check-in`;
      latestDetails.textContent = GUEST_WELLNESS_MESSAGE;
    } else {
      const row = latest.data;
      latestStatus.textContent = `${formatNotificationTimestamp(latest)} — ${row.approval_status || "Pending"}`;
      latestDetails.textContent = ["Scheduled", "Confirmed", "Rescheduled"].includes(row.approval_status)
        ? `Confirmed schedule: ${formatRequestDate(row.confirmed_date || row.requested_date)} · ${formatRequestTime(row.confirmed_time || row.requested_time_slot)}`
        : `Requested: ${formatRequestDate(row.requested_date)} · ${formatRequestTime(row.requested_time_slot)}`;
    }
    notificationLatest.append(latestHeading, latestStatus, latestDetails);
  }

  if (requestHistoryError) {
    const message = document.createElement("p");
    message.className = "notification-empty notification-error";
    message.textContent = "Could not refresh request history. Showing the last loaded requests.";
    notificationHistory.append(message);
  }
  items.forEach(renderNotificationItem);
}

function markRequestStatesSeen() {
  seenRequestStates = new Map(requestRows.map((row) => [row.request_id, requestSignature(row)]));
  const storageKey = currentSession
    ? `patient-request-seen:${currentSession.user.id}`
    : GUEST_REQUEST_SEEN_KEY;
  if (!currentSession) {
    guestWellnessItems.forEach((item) => {
      seenRequestStates.set(`wellness:${item.id}`, item.created_at);
    });
  }
  try {
    localStorage.setItem(
      storageKey,
      JSON.stringify(Object.fromEntries(seenRequestStates))
    );
  } catch (error) {
    console.error("Could not save request notification state.", error);
  }
  updateNotificationBadge();
}

function setNotificationPopoverOpen(isOpen) {
  notificationPopover.hidden = !isOpen;
  notificationButton.setAttribute("aria-expanded", String(isOpen));
  if (isOpen && requestHistoryLoaded) markRequestStatesSeen();
}

function setAccountPopoverOpen(isOpen) {
  accountPopover.hidden = !isOpen;
  accountButton.setAttribute("aria-expanded", String(isOpen));
}

function loadSeenRequestStates(userId) {
  seenRequestStates = new Map();
  try {
    const stored = JSON.parse(localStorage.getItem(`patient-request-seen:${userId}`) || "{}");
    if (stored && typeof stored === "object" && !Array.isArray(stored)) {
      seenRequestStates = new Map(Object.entries(stored).map(([id, signature]) => [id, String(signature)]));
    }
  } catch (error) {
    console.error("Could not load request notification state.", error);
  }
}

function readGuestRequestTokens() {
  try {
    const saved = JSON.parse(localStorage.getItem(GUEST_REQUEST_TOKENS_KEY) || "[]");
    if (!Array.isArray(saved)) {
      throw new TypeError("Guest request tokens are not a list.");
    }
    return [...new Set(saved.filter(
      (token) => typeof token === "string" && token.length >= 24
    ))];
  } catch (error) {
    console.error("Could not read guest request tokens.", error);
    return [];
  }
}

function saveGuestRequestToken(token) {
  try {
    const tokens = readGuestRequestTokens();
    if (!tokens.includes(token)) tokens.push(token);
    localStorage.setItem(GUEST_REQUEST_TOKENS_KEY, JSON.stringify(tokens));
    return true;
  } catch (error) {
    console.error("Could not save the guest request reference.", error);
    return false;
  }
}

function clearGuestRequestTokens() {
  try {
    localStorage.removeItem(GUEST_REQUEST_TOKENS_KEY);
  } catch (error) {
    console.error("Could not clear guest request tokens.", error);
    throw error;
  }
}

function readGuestWellnessItems() {
  try {
    const saved = JSON.parse(localStorage.getItem(GUEST_WELLNESS_ITEMS_KEY) || "[]");
    if (!Array.isArray(saved)) {
      throw new TypeError("Guest wellness check-ins are not a list.");
    }
    return saved.filter((item) =>
      item &&
      typeof item.id === "string" &&
      typeof item.created_at === "string" &&
      Number.isFinite(new Date(item.created_at).getTime())
    );
  } catch (error) {
    console.error("Could not read guest wellness check-ins.", error);
    return [];
  }
}

function loadGuestSeenRequestStates() {
  seenRequestStates = new Map();
  try {
    const saved = JSON.parse(localStorage.getItem(GUEST_REQUEST_SEEN_KEY) || "{}");
    if (saved && typeof saved === "object" && !Array.isArray(saved)) {
      seenRequestStates = new Map(
        Object.entries(saved).map(([id, signature]) => [id, String(signature)])
      );
    }
  } catch (error) {
    console.error("Could not load guest notification state.", error);
  }
}

async function loadGuestRequestHistory() {
  if (currentSession) return;
  const wasLoaded = requestHistoryLoaded;
  const previousRows = requestRows;
  const loadId = ++requestLoadSequence;
  requestRows = wasLoaded ? previousRows : [];
  requestHistoryLoaded = wasLoaded;
  requestHistoryError = false;
  loadGuestSeenRequestStates();
  guestWellnessItems = readGuestWellnessItems();
  renderRequestHistory(requestRows);

  const tokens = readGuestRequestTokens();
  if (!tokens.length || !supabase) {
    requestRows = [];
    requestHistoryLoaded = true;
    renderRequestHistory(requestRows);
    updateNotificationBadge();
    if (!notificationPopover.hidden) markRequestStatesSeen();
    return;
  }

  try {
    const { data, error } = await supabase.rpc(
      "get_guest_request_updates",
      { tokens }
    );
    if (error) throw error;
    if (currentSession || loadId !== requestLoadSequence) return;
    requestRows = (data || [])
      .filter((row) =>
        row &&
        typeof row.id === "string" &&
        ["Confirmed", "Rescheduled", "Declined"].includes(row.status)
      )
      .map((row) => ({
        request_id: row.id,
        requested_date: row.preferred_date,
        requested_time_slot: row.preferred_time,
        confirmed_date: row.confirmed_date,
        confirmed_time: row.confirmed_time,
        approval_status: row.status,
        created_at: row.created_at,
        guest: true
      }));
    requestHistoryLoaded = true;
    renderRequestHistory(requestRows);
    updateNotificationBadge();
    if (!notificationPopover.hidden) markRequestStatesSeen();
  } catch (error) {
    if (currentSession || loadId !== requestLoadSequence) return;
    console.error("Could not load guest request history.", error);
    requestHistoryLoaded = true;
    requestHistoryError = true;
    renderRequestHistory(requestRows);
    updateNotificationBadge();
  }
}

function stopRequestPolling() {
  window.clearInterval(requestPollingTimer);
  requestPollingTimer = null;
  requestLoadSequence += 1;
  setNotificationPopoverOpen(false);
  requestRows = [];
  seenRequestStates = new Map();
  requestHistoryLoaded = false;
  requestHistoryError = false;
  notificationLatest.replaceChildren();
  notificationHistory.replaceChildren();
  notificationRequestCount.textContent = "0 requests";
  updateNotificationBadge();
}

function startRequestPolling(session) {
  window.clearInterval(requestPollingTimer);
  requestPollingTimer = window.setInterval(() => {
    if (!document.hidden && currentSession && currentSession.user.id === session.user.id) {
      loadRequestHistory(session).catch((error) => {
        console.error("Could not refresh request history.", error);
        showRequestHistoryError(session.user.id);
      });
    }
  }, 15000);
}

function startGuestRequestPolling() {
  window.clearInterval(requestPollingTimer);
  requestPollingTimer = window.setInterval(() => {
    if (!document.hidden && !currentSession) loadGuestRequestHistory();
  }, 15000);
}

function showRequestHistoryError(userId) {
  if (!currentSession || currentSession.user.id !== userId) return;
  requestHistoryLoaded = true;
  requestHistoryError = true;
  renderRequestHistory(requestRows);
}

notificationButton.addEventListener("click", () => {
  setAccountPopoverOpen(false);
  setNotificationPopoverOpen(notificationPopover.hidden);
});
accountButton.addEventListener("click", () => {
  setNotificationPopoverOpen(false);
  setAccountPopoverOpen(accountPopover.hidden);
});
document.addEventListener("click", (event) => {
  if (!notificationMenu.contains(event.target)) setNotificationPopoverOpen(false);
  if (!accountMenu.contains(event.target)) setAccountPopoverOpen(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !notificationPopover.hidden) {
    setNotificationPopoverOpen(false);
    notificationButton.focus();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !accountPopover.hidden) {
    setAccountPopoverOpen(false);
    accountButton.focus();
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    if (currentSession) {
      const userId = currentSession.user.id;
      loadRequestHistory(currentSession).catch((error) => {
        console.error("Could not refresh request history.", error);
        showRequestHistoryError(userId);
      });
    } else {
      loadGuestRequestHistory();
    }
  }
});

function updateAccountCopy() {
  const isGuest = !currentSession;
  const isPrivateFlow = form.querySelector('input[name="next-step"]:checked').value === "private";
  const userMetadata = currentSession ? currentSession.user.user_metadata : null;
  document.querySelector("#entry-hint-prefix").textContent = currentSession
    ? "Your private entries are backed up to your account and are not sent to the center."
    : "Your words stay on this device unless you ask for help or ";
  textareaGuestPrompt.hidden = !isGuest;
  privateEntrySigninHelper.hidden = !isGuest || !isPrivateFlow;
  document.querySelector("#private-note-copy").textContent = currentSession
    ? "Your entry is saved on this device and backed up to your account. It is not sent to the center. You can remove it at any time."
    : "Your entry is saved only in this browser on this device for up to 30 days. It is not sent to the center. You can remove it at any time.";
  document.querySelector("#history-retention-note").textContent = currentSession
    ? "Backed-up entries remain in your account until removed. This device copy may be cleared with browser data."
    : "Entries saved as a guest remain on this device for 30 days. Clearing browser data removes them sooner.";
  wellnessEmailSetting.hidden = isGuest;
  wellnessEmailOptIn.checked = Boolean(userMetadata && userMetadata.wellness_email_opt_in === true);
}

function refreshGuestImportBanner() {
  if (!currentSession) {
    guestImportBanner.hidden = true;
    return;
  }
  const hasGuestEntries = privateEntries.getGuestEntries().length > 0;
  const hasGuestRequests = readGuestRequestTokens().length > 0;
  guestImportBanner.hidden =
    guestImportDismissed || (!hasGuestEntries && !hasGuestRequests);
  if (hasGuestEntries && hasGuestRequests) {
    guestImportCopy.textContent = "You have guest entries and requests saved on this device.";
  } else if (hasGuestEntries) {
    guestImportCopy.textContent = "You have guest entries saved on this device.";
  } else if (hasGuestRequests) {
    guestImportCopy.textContent = "You have guest requests saved on this device.";
  }
}

function createGuestRequestToken() {
  const cryptoApi = globalThis.crypto;
  if (!cryptoApi) throw new Error("Secure random tokens are unavailable in this browser.");
  if (typeof cryptoApi.randomUUID === "function") return cryptoApi.randomUUID();
  if (typeof cryptoApi.getRandomValues !== "function") {
    throw new Error("Secure random tokens are unavailable in this browser.");
  }

  const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function handleGuestWellnessMilestone(count) {
  if (currentSession || count < 5 || count % 5 !== 0) return;
  const item = {
    id: `${count}-${Date.now()}`,
    entry_count: count,
    created_at: new Date().toISOString()
  };
  guestWellnessItems = [...readGuestWellnessItems(), item];
  try {
    localStorage.setItem(GUEST_WELLNESS_ITEMS_KEY, JSON.stringify(guestWellnessItems));
  } catch (error) {
    console.error("Could not save the guest wellness check-in.", error);
  }
  guestWellnessMessage.textContent = GUEST_WELLNESS_MESSAGE;
  guestWellnessBanner.hidden = false;
  renderRequestHistory(requestRows);
  updateNotificationBadge();
}

async function importGuestData() {
  if (!currentSession || !supabase) return;
  const session = currentSession;
  const tokens = readGuestRequestTokens();
  guestImportButton.disabled = true;
  guestImportStatus.textContent = "Importing your saved guest data…";
  try {
    if (privateEntries.getGuestEntries().length) {
      await privateEntries.importGuestEntries(supabase, session.user);
    }
    if (!currentSession || currentSession.user.id !== session.user.id) return;
    if (tokens.length) {
      const { error } = await supabase.rpc("claim_guest_requests", { tokens });
      if (error) throw error;
    }
    if (!currentSession || currentSession.user.id !== session.user.id) return;
    privateEntries.clearGuestEntries();
    clearGuestRequestTokens();
    guestImportDismissed = true;
    guestImportBanner.hidden = true;
    privateEntries.setUser(session.user);
    privateEntries.render();
    try {
      await loadRequestHistory(session);
    } catch (error) {
      console.error("Guest data was imported, but request history could not be refreshed.", error);
      showRequestHistoryError(session.user.id);
    }
    refreshGuestImportBanner();
    showFeedback("Your guest entries and requests were imported to your account.", "success");
  } catch (error) {
    console.error("Could not import guest data.", error);
    if (currentSession && currentSession.user.id === session.user.id) {
      guestImportStatus.textContent = "Import could not be completed. You can safely retry; guest data that has not been imported remains on this device.";
    }
  } finally {
    guestImportButton.disabled = false;
  }
}

guestImportButton.addEventListener("click", importGuestData);
guestImportDismiss.addEventListener("click", () => {
  guestImportDismissed = true;
  guestImportBanner.hidden = true;
});
guestWellnessAssistant.addEventListener("click", () => {
  document.querySelector(".care-chatbot-toggle")?.click();
});
guestWellnessCallback.addEventListener("click", () => {
  activateView(viewTabs[0]);
  form.querySelector('input[name="next-step"][value="help"]').checked = true;
  setFlow("help");
  document.querySelector("#callback-panel").scrollIntoView({ behavior: "smooth", block: "start" });
});
guestWellnessDismiss.addEventListener("click", () => {
  guestWellnessBanner.hidden = true;
});

function clearSignedInUiState(showGuestEntries = true) {
  currentSession = null;
  stopRequestPolling();
  setAccountPopoverOpen(false);
  privateEntries.setUser(null);
  if (!showGuestEntries) privateEntries.clearDisplay();
  privateEntries.clearLegacyStorage();

  form.reset();
  callbackSchedule.reset();
  countLabel.textContent = "0 / 10,000";
  setFlow("private");
  entryToast.hidden = true;
  window.clearTimeout(toastTimeout);
  hideFeedback();

  authForm.reset();
  setAuthMode("signin");
  authError.hidden = true;
  authError.textContent = "";
  authEmail.textContent = "";
  authEmail.title = "";
  wellnessEmailStatus.textContent = "";
  wellnessEmailStatus.classList.remove("error");
  wellnessEmailOptIn.checked = false;
  wellnessEmailOptIn.disabled = false;
  authOpenButton.hidden = false;
  authAccount.hidden = true;
  notificationButton.hidden = false;
  historySigninBanner.hidden = false;
  guestWellnessItems = [];
  guestWellnessBanner.hidden = true;
  guestImportBanner.hidden = true;
  guestImportStatus.textContent = "";
  guestImportDismissed = false;
  if (authDialog.open) authDialog.close();
  window.dispatchEvent(new Event("patient-portal:session-cleared"));
  authReady = true;
  if (showGuestEntries) {
    loadGuestRequestHistory();
    if (supabase && readGuestRequestTokens().length) startGuestRequestPolling();
  }
}

function escapeLikePattern(value) {
  return value.replace(/[\\%_]/g, "\\$&");
}

async function loadRequestHistory(session) {
  const userId = session.user.id;
  const loadId = ++requestLoadSequence;
  const email = typeof session.user.email === "string"
    ? session.user.email.trim()
    : "";
  const linkedRequestQuery = supabase
      .from("patient_help_requests")
      .select("request_id, requested_date, requested_time_slot, approval_status, created_at, updated_at")
      .eq("patient_user_id", userId)
      .order("created_at", { ascending: false });
  const legacyRequestQuery = email
    ? supabase
      .from("patient_help_requests")
      .select("request_id, requested_date, requested_time_slot, approval_status, created_at, updated_at")
      .is("patient_user_id", null)
      .ilike("patient_email", escapeLikePattern(email))
      .order("created_at", { ascending: false })
    : Promise.resolve({ data: [], error: null });
  const appointmentQuery = supabase
      .from("appointments")
      .select("appointment_id, requested_date, requested_time_slot, approval_status, created_at, updated_at")
      .eq("patient_user_id", userId)
      .order("created_at", { ascending: false });
  const [requestResult, legacyRequestResult, appointmentResult] = await Promise.all([
    linkedRequestQuery,
    legacyRequestQuery,
    appointmentQuery
  ]);
  if (requestResult.error) throw requestResult.error;
  if (legacyRequestResult.error) throw legacyRequestResult.error;
  if (appointmentResult.error) throw appointmentResult.error;
  if (currentSession && currentSession.user.id === userId && loadId === requestLoadSequence) {
    const uniqueRequests = new Map();
    [
      ...(requestResult.data || []),
      ...(legacyRequestResult.data || [])
    ].forEach((row) => uniqueRequests.set(row.request_id, row));
    requestRows = [
      ...uniqueRequests.values(),
      ...(appointmentResult.data || []).map((row) => ({
        ...row,
        request_id: `appointment:${row.appointment_id}`
      }))
    ];
    requestHistoryLoaded = true;
    requestHistoryError = false;
    renderRequestHistory(requestRows);
    updateNotificationBadge();
    if (!notificationPopover.hidden) markRequestStatesSeen();
  }
}

async function handleSignedInSession(session, forceSync = false) {
  if (!forceSync && session && currentSession && currentSession.user.id === session.user.id) {
    currentSession = session;
    authReady = true;
    updateAccountCopy();
    return;
  }
  if (!session) {
    clearSignedInUiState();
    return;
  }
  if (currentSession && currentSession.user.id !== session.user.id) {
    clearSignedInUiState(false);
  }
  const previousUserId = currentSession ? currentSession.user.id : null;
  const userChanged = previousUserId !== session.user.id;
  currentSession = session;
  authReady = true;
  if (userChanged) {
    setNotificationPopoverOpen(false);
    setAccountPopoverOpen(false);
    stopRequestPolling();
    guestWellnessItems = [];
    privateEntries.setUser(session.user);
    renderRequestHistory(requestRows);
    guestImportDismissed = false;
    guestImportStatus.textContent = "";
  }
  updateAccountCopy();
  wellnessEmailStatus.textContent = "";
  wellnessEmailStatus.classList.remove("error");
  authOpenButton.hidden = true;
  authAccount.hidden = false;
  notificationButton.hidden = false;
  historySigninBanner.hidden = true;
  guestWellnessBanner.hidden = true;
  refreshGuestImportBanner();
  entryToast.hidden = true;

  loadSeenRequestStates(session.user.id);
  startRequestPolling(session);
  authEmail.textContent = session.user.email || "";
  authEmail.title = session.user.email || "";
  try {
    await privateEntries.sync(supabase, session.user.id);
    if (currentSession && currentSession.user.id === session.user.id) {
      privateEntries.render();
    }
  } catch (error) {
    console.error("Could not sync journal entries.", error);
    if (currentSession && currentSession.user.id === session.user.id) {
      showFeedback("You’re signed in, but your entries could not be backed up. They remain saved on this device; try again when your connection is available.", "error");
    }
  }
  try {
    await loadRequestHistory(session);
  } catch (error) {
    console.error("Could not load request history.", error);
    showRequestHistoryError(session.user.id);
  }
}

async function syncSignedInSession() {
  if (currentSession) await handleSignedInSession(currentSession, true);
}

viewTabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateView(tab));
  tab.addEventListener("keydown", (event) => {
    let nextIndex;
    if (event.key === "ArrowRight") {
      nextIndex = (index + 1) % viewTabs.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + viewTabs.length) % viewTabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = viewTabs.length - 1;
    } else {
      return;
    }
    event.preventDefault();
    activateView(viewTabs[nextIndex], true);
  });
});
activateView(viewTabs.find((tab) => tab.getAttribute("aria-selected") === "true"));

document
  .querySelector(".hero-actions a[href=\"#share\"]")
  .addEventListener("click", () => {
    activateView(viewTabs[0]);
  });

const callCenterButton = document.querySelector("#call-center-button");
const contactDialog = document.querySelector("#contact-dialog");
const mobileUserAgent = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);

callCenterButton.addEventListener("click", (event) => {
  if (window.innerWidth > 768 || !mobileUserAgent) {
    event.preventDefault();
    contactDialog.showModal();
  }
});

document.querySelector("#contact-dialog-close").addEventListener("click", () => {
  contactDialog.close();
});
contactDialog.addEventListener("click", (event) => {
  if (event.target === contactDialog) contactDialog.close();
});

document.querySelectorAll("[data-open-auth]").forEach((button) => {
  button.addEventListener("click", openAuthDialog);
});
document.querySelector("#auth-dialog-close").addEventListener("click", () => authDialog.close());
authDialog.addEventListener("click", (event) => {
  if (event.target === authDialog) authDialog.close();
});
document.querySelector("#wellness-email-opt-in").addEventListener("change", async () => {
  if (!supabase || !currentSession) return;
  const requestedOptIn = wellnessEmailOptIn.checked;
  wellnessEmailOptIn.disabled = true;
  wellnessEmailStatus.classList.remove("error");
  wellnessEmailStatus.textContent = "Saving your preference…";
  try {
    const { data, error } = await supabase.auth.updateUser({
      data: { wellness_email_opt_in: requestedOptIn }
    });
    if (error) throw error;
    if (data.user) currentSession = { ...currentSession, user: data.user };
    wellnessEmailStatus.textContent = requestedOptIn
      ? "Wellness check-in emails are enabled."
      : "Wellness check-in emails are turned off.";
  } catch (error) {
    console.error("Could not update the wellness email preference.", error);
    wellnessEmailOptIn.checked = !requestedOptIn;
    wellnessEmailStatus.textContent = "Could not save your preference. Please try again.";
    wellnessEmailStatus.classList.add("error");
  } finally {
    wellnessEmailOptIn.disabled = false;
  }
});
authModeTabs.forEach(({ element, mode }, index) => {
  element.addEventListener("click", () => {
    setAuthMode(mode);
    authError.hidden = true;
    authError.textContent = "";
  });
  element.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const nextIndex = event.key === "ArrowRight"
      ? (index + 1) % authModeTabs.length
      : (index - 1 + authModeTabs.length) % authModeTabs.length;
    const nextTab = authModeTabs[nextIndex];
    setAuthMode(nextTab.mode);
    nextTab.element.focus();
    authError.hidden = true;
    authError.textContent = "";
  });
});
authPasswordToggle.addEventListener("click", () => {
  const isShowing = authPasswordInput.type === "password";
  authPasswordInput.type = isShowing ? "text" : "password";
  authPasswordToggle.setAttribute("aria-label", isShowing ? "Hide password" : "Show password");
  authPasswordToggle.setAttribute("aria-pressed", String(isShowing));
});
document.querySelector("#auth-signout").addEventListener("click", async () => {
  if (!supabase) return;
  clearSignedInUiState();
  try {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  } catch (error) {
    console.error("Could not sign out.", error);
    try {
      const { data, error: sessionError } = await supabase.auth.getSession();
      if (sessionError) throw sessionError;
      if (data.session) await handleSignedInSession(data.session, true);
    } catch (restoreError) {
      console.error("Could not restore the signed-in session.", restoreError);
    }
    showFeedback("You could not be signed out. Please try again.", "error");
  }
});
document.querySelector("#toast-close").addEventListener("click", () => {
  window.clearTimeout(toastTimeout);
  entryToast.hidden = true;
});

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!supabase || authUnavailable) {
    authError.textContent = "Sign-in is unavailable right now. You can continue using the portal as a guest.";
    authError.hidden = false;
    return;
  }
  authError.hidden = true;
  authSubmit.disabled = true;
  const email = document.querySelector("#auth-input-email").value.trim();
  const password = document.querySelector("#auth-input-password").value;
  try {
    const result = authMode === "signup"
      ? await supabase.auth.signUp({
        email,
        password,
        options: {
          data: { wellness_email_opt_in: authWellnessOptIn.checked }
        }
      })
      : await supabase.auth.signInWithPassword({ email, password });
    if (result.error) throw result.error;
    if (authMode === "signup" && !result.data.session) {
      authError.textContent = "Check your email for a confirmation link, then sign in here.";
      authError.hidden = false;
      return;
    }
    if (result.data.session) {
      await handleSignedInSession(result.data.session);
    }
    authDialog.close();
    authForm.reset();
    setAuthMode("signin");
  } catch (error) {
    console.error("Authentication failed.", error);
    authError.textContent = error.message || "We couldn’t complete sign-in. Please check your details and try again.";
    authError.hidden = false;
  } finally {
    authSubmit.disabled = false;
  }
});

document.querySelector("#copy-number-button").addEventListener("click", async () => {
  const copyStatus = document.querySelector("#copy-number-status");
  try {
    await navigator.clipboard.writeText("0920-691-5015");
    copyStatus.textContent = "Number copied.";
  } catch {
    copyStatus.textContent = "Copying isn’t available here. You can call 0920-691-5015 directly.";
  }
});

function setFlow(value) {
  const isHelp = value === "help";
  updateAccountCopy();
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
  if (!authReady) {
    showFeedback("Your account is still loading. Please try again in a moment.", "error");
    return;
  }
  const mode = form.querySelector('input[name="next-step"]:checked').value;
  const text = messageField.value.trim();
  if (!text) {
    showFeedback("Write a little about what’s on your mind before continuing.", "error");
    messageField.focus();
    return;
  }

  if (mode === "help") {
    let guestToken = null;
    if (!currentSession) {
      try {
        guestToken = createGuestRequestToken();
      } catch (error) {
        console.error("Could not create a secure guest request reference.", error);
        showFeedback("A secure request reference could not be created in this browser. Please try again or call the center.", "error");
        return;
      }
    }
    let guestTokenSaveFailed = false;
    await sendHelpRequest({
      form,
      messageField,
      session: currentSession,
      guestToken,
      showFeedback,
      hideFeedback,
      onSuccess: () => {
        if (guestToken) {
          guestTokenSaveFailed = !saveGuestRequestToken(guestToken);
          if (!guestTokenSaveFailed) {
            if (currentSession) {
              refreshGuestImportBanner();
            } else {
              loadGuestRequestHistory();
              startGuestRequestPolling();
            }
          }
        }
        form.reset();
        callbackSchedule.reset();
        setFlow("help");
        countLabel.textContent = "0 / 10,000";
        if (currentSession) {
          const session = currentSession;
          loadRequestHistory(session).catch((error) => {
            console.error("Could not refresh request history.", error);
            showRequestHistoryError(session.user.id);
          });
        }
      }
    });
    if (guestTokenSaveFailed) {
      showFeedback("Your request was sent, but this browser could not save its private notification reference. Please save your request details or call the center for updates.", "error");
    }
    return;
  }

  if (!privateEntries.save(text)) return;
  const engagementRequest = recordPortalEngagement("no_help_submitted");
  privateEntries.render();
  form.reset();
  form.querySelector('input[name="next-step"][value="private"]').checked = true;
  countLabel.textContent = "0 / 10,000";
  setFlow("private");
  showFeedback("Your private entry was saved on this device only. It will be removed from this list after 30 days.", "success");
  await engagementRequest;
  if (currentSession) {
    try {
      await privateEntries.sync(supabase, currentSession.user.id);
      privateEntries.render();
      showFeedback("Your private entry was saved and backed up to your account.", "success");
    } catch (error) {
      console.error("Could not back up the new journal entry.", error);
      showFeedback("Your entry is saved on this device, but couldn’t be backed up just now. It will remain here for 30 days.", "error");
    }
  } else {
    entryToast.hidden = false;
    window.clearTimeout(toastTimeout);
    toastTimeout = window.setTimeout(() => {
      entryToast.hidden = true;
    }, 8000);
  }
});

setFlow(form.querySelector('input[name="next-step"]:checked').value);
callbackSchedule.render();
setAuthMode("signin");
async function initializeAuth() {
  if (!config.supabaseUrl || !config.supabaseAnonKey) {
    authUnavailable = true;
    await handleSignedInSession(null);
    authError.textContent = "Sign-in is temporarily unavailable. You can continue using the portal as a guest.";
    if (privateEntries.storageUnavailable) {
      showFeedback("This browser could not access device storage. Private entries cannot be saved here.", "error");
    }
    return;
  }
  try {
    const { createClient } = await import("https://esm.sh/@supabase/supabase-js@2");
    supabase = createClient(config.supabaseUrl, config.supabaseAnonKey);
    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    await handleSignedInSession(data.session);
    if (privateEntries.storageUnavailable) {
      showFeedback("This browser could not access device storage. Private entries cannot be saved here.", "error");
    }
    supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_OUT") {
        clearSignedInUiState();
        return;
      }
      if (
        session &&
        currentSession &&
        currentSession.user.id !== session.user.id
      ) {
        authReady = false;
        clearSignedInUiState(false);
        authReady = false;
      }
      window.setTimeout(() => {
        handleSignedInSession(session).catch((error) => {
          console.error("Could not load the signed-in account.", error);
          if (session && currentSession?.user.id === session.user.id) {
            showFeedback("Your account data could not be loaded. Please try again.", "error");
          }
        });
      }, 0);
    });
    window.addEventListener("online", () => {
      if (currentSession) {
        syncSignedInSession().catch((error) => {
          console.error("Could not retry journal sync.", error);
          showFeedback("Your entries could not be backed up yet. Please try again later.", "error");
        });
      } else {
        loadGuestRequestHistory();
      }
    });
  } catch (error) {
    console.error("Could not initialize Supabase sign-in.", error);
    await handleSignedInSession(null);
    authUnavailable = true;
    authError.textContent = "Sign-in is temporarily unavailable. You can continue using the portal as a guest.";
    authError.hidden = false;
    if (privateEntries.storageUnavailable) {
      showFeedback("This browser could not access device storage. Private entries cannot be saved here.", "error");
    }
  }
}

initializeAuth();
