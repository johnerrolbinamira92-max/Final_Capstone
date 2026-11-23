import { sendHelpRequest } from "./features/callback-request.js";
import { initCallbackSchedule } from "./features/callback-schedule.js";
import { createPrivateEntries } from "./features/private-entries.js";
import { initTheme } from "./features/theme.js";
import { hideFeedback, showFeedback } from "./ui/feedback.js";

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
const notificationMenu = document.querySelector(".notification-menu");
const notificationButton = document.querySelector("#notification-button");
const notificationBadge = document.querySelector("#notification-badge");
const notificationPopover = document.querySelector("#notification-popover");
const notificationLatest = document.querySelector("#notification-latest");
const notificationHistory = document.querySelector("#notification-history");
const notificationRequestCount = document.querySelector("#notification-request-count");
const historySigninBanner = document.querySelector("#history-signin-banner");
const textareaGuestPrompt = document.querySelector("#textarea-guest-prompt");
const privateEntrySigninHelper = document.querySelector("#private-entry-signin-helper");
const entryToast = document.querySelector("#entry-toast");
const config = window.PATIENT_PORTAL_CONFIG || {};
let supabase = null;
let authUnavailable = false;
let currentSession = null;
let authMode = "signin";
let toastTimeout;
let requestPollingTimer = null;
let requestLoadSequence = 0;
let requestRows = [];
let seenRequestStates = new Map();
let requestHistoryLoaded = false;
let requestHistoryError = false;

const privateEntries = createPrivateEntries({
  historyElement: document.querySelector("#entry-history"),
  onStorageError: (message) => showFeedback(message, "error"),
  onRemove: async (entry) => {
    if (!entry.cloudSynced || !currentSession) return true;
    const { error } = await supabase
      .from("patient_journal_entries")
      .delete()
      .eq("user_id", currentSession.user.id)
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

function activateView(tab, moveFocus = false) {
  viewTabs.forEach((candidate) => {
    const isActive = candidate === tab;
    candidate.setAttribute("aria-selected", String(isActive));
    candidate.tabIndex = isActive ? 0 : -1;
    document.getElementById(
      candidate.getAttribute("aria-controls")
    ).hidden = !isActive;
  });
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
  return `${row.approval_status || "Pending"}|${row.updated_at || row.created_at || ""}`;
}

function requestHasUnreadUpdate(row) {
  const signature = requestSignature(row);
  const seenSignature = seenRequestStates.get(row.request_id);
  if (seenSignature !== undefined) return seenSignature !== signature;
  if ((row.approval_status || "Pending") === "Pending" || !row.updated_at || !row.created_at) return false;
  return new Date(row.updated_at).getTime() > new Date(row.created_at).getTime();
}

function updateNotificationBadge() {
  const unreadCount = requestRows.filter(requestHasUnreadUpdate).length;
  notificationBadge.hidden = unreadCount === 0;
  notificationBadge.textContent = unreadCount > 9 ? "9+" : String(unreadCount);
  notificationButton.setAttribute(
    "aria-label",
    unreadCount ? `Request notifications, ${unreadCount} unread updates` : "Request notifications"
  );
}

function renderRequestHistory(rows) {
  notificationLatest.replaceChildren();
  notificationHistory.replaceChildren();
  notificationRequestCount.textContent = `${rows.length} ${rows.length === 1 ? "request" : "requests"}`;

  if (!requestHistoryLoaded) {
    const heading = document.createElement("h2");
    heading.textContent = "Your requests";
    const message = document.createElement("p");
    message.className = "notification-empty";
    message.textContent = "Loading your requests…";
    notificationLatest.append(heading);
    notificationHistory.append(message);
    return;
  }

  if (requestHistoryError && !rows.length) {
    const heading = document.createElement("h2");
    heading.textContent = "Your requests";
    const message = document.createElement("p");
    message.className = "notification-empty notification-error";
    message.textContent = "Request history couldn’t be loaded. Please try again later.";
    notificationLatest.append(heading);
    notificationHistory.append(message);
    return;
  }

  if (!rows.length) {
    const heading = document.createElement("h2");
    heading.textContent = "Your requests";
    const message = document.createElement("p");
    message.className = "notification-empty";
    message.textContent = "You haven’t submitted any callback requests yet.";
    notificationLatest.append(heading);
    notificationHistory.append(message);
    return;
  }

  const updatedRows = rows.filter((row) =>
    row.updated_at && row.created_at &&
    new Date(row.updated_at).getTime() > new Date(row.created_at).getTime()
  );
  const latestCandidates = updatedRows.length ? updatedRows : rows;
  const latest = latestCandidates.reduce((mostRecent, row) => {
    const rowTime = new Date(row.updated_at || row.created_at || 0).getTime();
    const latestTime = new Date(mostRecent.updated_at || mostRecent.created_at || 0).getTime();
    return rowTime >= latestTime ? row : mostRecent;
  });
  const latestHeading = document.createElement("p");
  latestHeading.className = "notification-eyebrow";
  latestHeading.textContent = "Latest update";
  const latestStatus = document.createElement("p");
  latestStatus.className = "notification-latest-status";
  latestStatus.textContent = `${formatRequestDate((latest.updated_at || latest.created_at || "").slice(0, 10))} — ${latest.approval_status || "Pending"}`;
  const latestDetails = document.createElement("p");
  latestDetails.className = "notification-latest-details";
  latestDetails.textContent = ["Scheduled", "Rescheduled"].includes(latest.approval_status)
    ? `Confirmed schedule: ${formatRequestDate(latest.requested_date)} · ${formatRequestTime(latest.requested_time_slot)}`
    : `Requested: ${formatRequestDate(latest.requested_date)} · ${formatRequestTime(latest.requested_time_slot)}`;
  notificationLatest.append(latestHeading, latestStatus, latestDetails);

  const chronologicalRows = [...rows].sort(
    (first, second) => new Date(first.created_at || 0) - new Date(second.created_at || 0)
  );
  if (requestHistoryError) {
    const message = document.createElement("p");
    message.className = "notification-empty notification-error";
    message.textContent = "Could not refresh request history. Showing the last loaded requests.";
    notificationHistory.append(message);
  }
  chronologicalRows.forEach((row) => {
    const item = document.createElement("article");
    item.className = "request-history-item";
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
    item.append(header, preferredTime);
    if (["Scheduled", "Rescheduled"].includes(row.approval_status)) {
      const confirmedSchedule = document.createElement("p");
      confirmedSchedule.className = "confirmed-schedule";
      confirmedSchedule.textContent = `Confirmed schedule: ${formatRequestDate(row.requested_date)} · ${formatRequestTime(row.requested_time_slot)}`;
      item.append(confirmedSchedule);
    }
    notificationHistory.append(item);
  });
}

function markRequestStatesSeen() {
  seenRequestStates = new Map(requestRows.map((row) => [row.request_id, requestSignature(row)]));
  if (currentSession) {
    try {
      localStorage.setItem(
        `patient-request-seen:${currentSession.user.id}`,
        JSON.stringify(Object.fromEntries(seenRequestStates))
      );
    } catch (error) {
      console.error("Could not save request notification state.", error);
    }
  }
  updateNotificationBadge();
}

function setNotificationPopoverOpen(isOpen) {
  notificationPopover.hidden = !isOpen;
  notificationButton.setAttribute("aria-expanded", String(isOpen));
  if (isOpen && requestHistoryLoaded) markRequestStatesSeen();
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

function stopRequestPolling() {
  window.clearInterval(requestPollingTimer);
  requestPollingTimer = null;
  requestLoadSequence += 1;
  setNotificationPopoverOpen(false);
  requestRows = [];
  requestHistoryLoaded = false;
  requestHistoryError = false;
  renderRequestHistory(requestRows);
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

function showRequestHistoryError(userId) {
  if (!currentSession || currentSession.user.id !== userId) return;
  requestHistoryLoaded = true;
  requestHistoryError = true;
  renderRequestHistory(requestRows);
}

notificationButton.addEventListener("click", () => {
  setNotificationPopoverOpen(notificationPopover.hidden);
});
document.addEventListener("click", (event) => {
  if (!notificationMenu.contains(event.target)) setNotificationPopoverOpen(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !notificationPopover.hidden) {
    setNotificationPopoverOpen(false);
    notificationButton.focus();
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && currentSession) {
    const userId = currentSession.user.id;
    loadRequestHistory(currentSession).catch((error) => {
      console.error("Could not refresh request history.", error);
      showRequestHistoryError(userId);
    });
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

async function loadRequestHistory(session) {
  const userId = session.user.id;
  const loadId = ++requestLoadSequence;
  const [requestResult, appointmentResult] = await Promise.all([
    supabase
      .from("patient_help_requests")
      .select("request_id, requested_date, requested_time_slot, approval_status, created_at, updated_at")
      .eq("patient_user_id", userId)
      .order("created_at", { ascending: false }),
    supabase
      .from("appointments")
      .select("appointment_id, requested_date, requested_time_slot, approval_status, created_at, updated_at")
      .eq("patient_user_id", userId)
      .order("created_at", { ascending: false })
  ]);
  if (requestResult.error) throw requestResult.error;
  if (appointmentResult.error) throw appointmentResult.error;
  if (currentSession && currentSession.user.id === userId && loadId === requestLoadSequence) {
    requestRows = [
      ...(requestResult.data || []),
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
    updateAccountCopy();
    return;
  }
  const previousUserId = currentSession ? currentSession.user.id : null;
  currentSession = session;
  if (!session || previousUserId !== session.user.id) {
    setNotificationPopoverOpen(false);
    requestRows = [];
    requestHistoryLoaded = false;
    requestHistoryError = false;
    renderRequestHistory(requestRows);
    updateNotificationBadge();
  }
  updateAccountCopy();
  wellnessEmailStatus.textContent = "";
  wellnessEmailStatus.classList.remove("error");
  const signedIn = Boolean(session);
  authOpenButton.hidden = signedIn;
  authAccount.hidden = !signedIn;
  notificationButton.hidden = !signedIn;
  historySigninBanner.hidden = signedIn;
  entryToast.hidden = true;
  if (!signedIn) {
    stopRequestPolling();
    return;
  }

  loadSeenRequestStates(session.user.id);
  startRequestPolling(session);
  authEmail.textContent = session.user.email || "";
  authEmail.title = session.user.email || "";
  try {
    const sync = privateEntries.sync(supabase, session.user.id);
    privateEntries.render();
    await sync;
    privateEntries.render();
  } catch (error) {
    console.error("Could not sync journal entries.", error);
    showFeedback("You’re signed in, but your entries could not be backed up. They remain saved on this device; try again when your connection is available.", "error");
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
  try {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  } catch (error) {
    console.error("Could not sign out.", error);
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
      session: currentSession,
      showFeedback,
      hideFeedback,
      onSuccess: () => {
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
    return;
  }

  if (!privateEntries.save(text, currentSession ? currentSession.user.id : null)) return;
  privateEntries.render();
  form.reset();
  form.querySelector('input[name="next-step"][value="private"]').checked = true;
  countLabel.textContent = "0 / 10,000";
  setFlow("private");
  showFeedback("Your private entry was saved on this device only. It will be removed from this list after 30 days.", "success");
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

initTheme();
setFlow(form.querySelector('input[name="next-step"]:checked').value);
callbackSchedule.render();
privateEntries.render();
setAuthMode("signin");
if (privateEntries.storageUnavailable) {
  showFeedback("This browser could not access device storage. Private entries cannot be saved here.", "error");
}
async function initializeAuth() {
  if (!config.supabaseUrl || !config.supabaseAnonKey) {
    authUnavailable = true;
    return;
  }
  try {
    const { createClient } = await import("https://esm.sh/@supabase/supabase-js@2");
    supabase = createClient(config.supabaseUrl, config.supabaseAnonKey);
    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    await handleSignedInSession(data.session);
    supabase.auth.onAuthStateChange((_event, session) => {
      window.setTimeout(() => {
        handleSignedInSession(session);
      }, 0);
    });
    window.addEventListener("online", () => {
      syncSignedInSession().catch((error) => {
        console.error("Could not retry journal sync.", error);
        showFeedback("Your entries could not be backed up yet. Please try again later.", "error");
      });
    });
  } catch (error) {
    console.error("Could not initialize Supabase sign-in.", error);
    authUnavailable = true;
    authError.textContent = "Sign-in is temporarily unavailable. You can continue using the portal as a guest.";
    authError.hidden = false;
  }
}

initializeAuth();
