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
const authAppointmentStatus = document.querySelector("#appointment-status");
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

function displayAppointmentUpdates(rows) {
  authAppointmentStatus.replaceChildren();
  if (!rows.length) {
    authAppointmentStatus.hidden = true;
    return;
  }

  const heading = document.createElement("strong");
  heading.textContent = "Appointment updates";
  const list = document.createElement("ul");
  rows.forEach((row) => {
    const item = document.createElement("li");
    const date = row.requested_date
      ? new Date(`${row.requested_date}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "medium" })
      : "Date not set";
    item.textContent = `${date} — ${row.approval_status || "Pending"}`;
    list.append(item);
  });
  authAppointmentStatus.append(heading, list);
  authAppointmentStatus.hidden = false;
}

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

async function loadAppointmentUpdates(session) {
  const userId = session.user.id;
  const [requestResult, appointmentResult] = await Promise.all([
    supabase
      .from("patient_help_requests")
      .select("requested_date, approval_status")
      .eq("patient_user_id", userId)
      .order("created_at", { ascending: false }),
    supabase
      .from("appointments")
      .select("requested_date, approval_status")
      .eq("patient_user_id", userId)
      .order("created_at", { ascending: false })
  ]);
  if (requestResult.error) throw requestResult.error;
  if (appointmentResult.error) throw appointmentResult.error;
  if (currentSession && currentSession.user.id === userId) {
    displayAppointmentUpdates([...requestResult.data, ...appointmentResult.data]);
  }
}

async function handleSignedInSession(session, forceSync = false) {
  if (!forceSync && session && currentSession && currentSession.user.id === session.user.id) {
    currentSession = session;
    updateAccountCopy();
    return;
  }
  currentSession = session;
  updateAccountCopy();
  wellnessEmailStatus.textContent = "";
  wellnessEmailStatus.classList.remove("error");
  const signedIn = Boolean(session);
  authOpenButton.hidden = signedIn;
  authAccount.hidden = !signedIn;
  historySigninBanner.hidden = signedIn;
  entryToast.hidden = true;
  if (!signedIn) {
    authAppointmentStatus.hidden = true;
    return;
  }

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
    await loadAppointmentUpdates(session);
  } catch (error) {
    console.error("Could not load appointment updates.", error);
    if (currentSession && currentSession.user.id === session.user.id) {
      authAppointmentStatus.textContent = "Appointment updates could not be loaded. Please try again later.";
      authAppointmentStatus.hidden = false;
    }
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
        if (currentSession) loadAppointmentUpdates(currentSession).catch((error) => {
          console.error("Could not refresh appointment updates.", error);
        });
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
