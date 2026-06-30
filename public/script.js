import { initPixelSoftUtilityApp } from "./design-system/app-shell.js";
import { bindRegisterWindow } from "./design-system/setup-flow.js";
import { setPixelSoftUtilityMode, setPixelSoftUtilityTheme } from "./design-system/theme-controller.js";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const MASKED_KEY = "\u25CF\u25CF\u25CF\u25CF\u25CF - \u25CF\u25CF\u25CF\u25CF\u25CF - \u25CF\u25CF\u25CF\u25CF\u25CF";

const appConfig = JSON.parse($("script[data-psu-app-config]").textContent);
const state = {
  user: null,
  authMode: "login",
  keys: [],
  filter: "available",
  query: "",
  sort: "name-asc",
  activeIndex: null,
  activeSecret: "",
  creating: false,
  settingsMode: "account",
};

const views = {
  setupError: $("#setup-error-view"),
  setup: $("#setup-view"),
  auth: $("#auth-view"),
  app: $("#app-view"),
};

const el = {
  setupForm: $("#setup-form"),
  setupSecret: $("#setup-secret"),
  setupMessage: $("#setup-message"),
  setupSubmit: $("#setup-submit"),
  setupHelpToggle: $("#setup-help-toggle"),
  setupHelp: $("#setup-help"),
  setupRetry: $("#setup-retry"),
  setupErrorCopy: $("#setup-error-copy"),
  setupErrorKey: $("#setup-error-key"),
  authTitle: $("#auth-title"),
  authForm: $("#auth-form"),
  authDisplayNameField: $("#auth-display-name-field"),
  authDisplayName: $("#auth-display-name"),
  authUsername: $("#auth-username"),
  authEmailField: $("#auth-email-field"),
  authEmail: $("#auth-email"),
  authPassword: $("#auth-password"),
  authMessage: $("#auth-message"),
  passwordResetRequest: $("#password-reset-request"),
  authModeToggle: $("#auth-mode-toggle"),
  authSubmit: $("#auth-submit"),
  rows: $("#rows"),
  search: $("#search"),
  sort: $("#sort"),
  statFree: $("#stat-free"),
  statUsed: $("#stat-used"),
  statTotal: $("#stat-total"),
  newKey: $("#new-key"),
  profileButton: $("#profile-button"),
  profileAvatar: $("#profile-avatar"),
  profileName: $("#profile-name"),
  profileId: $("#profile-id"),
  logout: $("#logout"),
  notificationsButton: $("#notifications-button"),
  notificationBadge: $("#notification-badge"),
  profileNotificationsRow: $("#profile-notifications-row"),
  notificationsBody: $("#notifications-body"),
  settingsTitle: $("#settings-title"),
  settingsBody: $("#settings-body"),
  detailDialog: $("#detail-dialog"),
  keyForm: $("#key-form"),
  detailTitle: $("#detail-title"),
  detailGame: $("#detail-game"),
  detailKey: $("#detail-key"),
  detailAdded: $("#detail-added"),
  detailRedeemed: $("#detail-redeemed"),
  detailRedeemedBy: $("#detail-redeemed-by"),
  detailReveal: $("#detail-reveal"),
  detailRedeem: $("#detail-redeem"),
  detailShare: $("#detail-share"),
  detailCopy: $("#detail-copy"),
  detailRequestReactivation: $("#detail-request-reactivation"),
  detailSteam: $("#detail-steam"),
  detailSteamDb: $("#detail-steamdb"),
  detailSave: $("#detail-save"),
  detailUnredeem: $("#detail-unredeem"),
  detailDelete: $("#detail-delete"),
  shareLinkRow: $("#share-link-row"),
  detailShareLink: $("#detail-share-link"),
  detailShareCopy: $("#detail-share-copy"),
  toast: $("#toast"),
  confirmDialog: $("#confirm-dialog"),
  confirmTitle: $("#confirm-title"),
  confirmMessage: $("#confirm-message"),
  confirmCancel: $("#confirm-cancel"),
  confirmOk: $("#confirm-ok"),
};

async function loadIconSprite() {
  const host = $("#icon-sprite");
  try {
    host.innerHTML = await fetch("/icons/psu-icons.svg", { cache: "no-cache" }).then((response) => response.text());
  } catch (_) {
    host.innerHTML = "";
  }
}

function hideAllViews() {
  Object.values(views).forEach((view) => { view.hidden = true; });
}

function showView(name) {
  hideAllViews();
  views[name].hidden = false;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function normalize(value) {
  return String(value || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function initials(user) {
  const source = user?.displayName || user?.username || "K";
  return source.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "K";
}

function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" });
}

function toDateTimeLocal(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function fromDateTimeLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

function steamSearchUrl(game) {
  return `https://store.steampowered.com/search/?term=${encodeURIComponent(game || "")}`;
}

function steamDbUrl(game) {
  return `https://steamdb.info/search/?a=app&q=${encodeURIComponent(game || "")}`;
}

function showToast(message, kind = "default") {
  el.toast.textContent = message;
  el.toast.className = `keyku-toast is-visible ${kind === "error" ? "is-error" : ""} ${kind === "success" ? "is-success" : ""}`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => el.toast.classList.remove("is-visible"), 3200);
}

async function readJsonResponse(response) {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch (_) {
    return {};
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await readJsonResponse(response);
  if (response.status === 401 && path !== "/api/auth/me") {
    setAuthMode("login");
    showView("auth");
    throw new Error(data.error || "Login required.");
  }
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function renderSetupError(status) {
  el.setupErrorCopy.textContent = status.message || "Setup secret is not configured.";
  el.setupErrorKey.textContent = status.errorKey || "ISHIKU_SETUP_SECRET";
  showView("setupError");
}

async function bootstrap() {
  initPixelSoftUtilityApp(appConfig);
  await loadIconSprite();
  bindSetupForm();
  bindEvents();
  await refreshSession();
}

async function refreshSession() {
  const setupStatus = await api("/api/setup/status");
  if (setupStatus.setupRequired) {
    if (!setupStatus.setupConfigured) {
      renderSetupError(setupStatus);
      return;
    }
    showView("setup");
    requestAnimationFrame(() => el.setupSecret.focus());
    return;
  }

  const session = await api("/api/auth/me");
  if (!session.authenticated) {
    setAuthMode("login");
    showView("auth");
    return;
  }
  showApp(session.user, session);
}

function bindSetupForm() {
  bindRegisterWindow(el.setupForm, {
    appId: appConfig.app_id,
    appName: appConfig.app_name,
    onSubmit: async (formData) => {
      el.setupSubmit.disabled = true;
      el.setupMessage.textContent = "";
      try {
        const data = await api("/api/setup/register-admin", {
          method: "POST",
          body: JSON.stringify({
            setupSecret: formData.get("setup_secret"),
            displayName: formData.get("admin_display_name"),
            adminUsername: formData.get("admin_username"),
            email: formData.get("admin_email"),
            password: formData.get("admin_password"),
            passwordConfirm: formData.get("admin_password_confirm"),
          }),
        });
        showToast("Admin account created", "success");
        el.setupForm.reset();
        showApp(data.user, data);
      } catch (error) {
        el.setupMessage.textContent = error.message;
      } finally {
        el.setupSubmit.disabled = false;
      }
    },
  });
}

function showApp(user, meta = {}) {
  state.user = user;
  showView("app");
  const userInitials = initials(user);
  el.profileButton.textContent = userInitials;
  el.profileAvatar.textContent = userInitials;
  el.profileName.textContent = user.displayName || user.username;
  el.profileId.textContent = `${user.username}${user.role === "admin" ? " - Admin" : ""}`;
  $$(".keyku-admin-only").forEach((node) => { node.hidden = user.role !== "admin"; });
  updateNotificationIndicator(meta.notificationCount || meta.pendingCount || 0);
  loadKeys();
}

function updateNotificationIndicator(count) {
  const value = Number(count || 0);
  const show = state.user?.role === "admin" && value > 0;
  el.notificationBadge.hidden = !show;
  el.notificationsButton.setAttribute("aria-label", show ? `Open notifications, ${value} pending` : "Open notifications");
}

function setAuthMode(mode) {
  state.authMode = mode === "request" ? "request" : "login";
  const requesting = state.authMode === "request";
  el.authTitle.textContent = requesting ? "Request account" : "Sign in";
  el.authDisplayNameField.hidden = !requesting;
  el.authEmailField.hidden = !requesting;
  el.passwordResetRequest.hidden = requesting;
  el.authModeToggle.textContent = requesting ? "Back to sign in" : "Request account";
  el.authSubmit.textContent = requesting ? "Send request" : "Sign in";
  el.authPassword.autocomplete = requesting ? "new-password" : "current-password";
  el.authMessage.textContent = "";
}

function bindEvents() {
  el.setupHelpToggle.addEventListener("click", () => {
    el.setupHelp.hidden = !el.setupHelp.hidden;
    el.setupHelpToggle.textContent = el.setupHelp.hidden ? "Show setup help" : "Hide setup help";
  });
  el.setupRetry.addEventListener("click", refreshSession);

  el.authModeToggle.addEventListener("click", () => {
    setAuthMode(state.authMode === "login" ? "request" : "login");
  });

  el.authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    el.authMessage.textContent = "";
    el.authSubmit.disabled = true;
    try {
      if (state.authMode === "request") {
        const data = await api("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({
            displayName: el.authDisplayName.value,
            username: el.authUsername.value,
            email: el.authEmail.value,
            password: el.authPassword.value,
          }),
        });
        el.authForm.reset();
        setAuthMode("login");
        el.authMessage.textContent = data.message || "Account request sent. An admin must approve it before you can sign in.";
        return;
      }
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: el.authUsername.value, password: el.authPassword.value }),
      });
      el.authForm.reset();
      showToast("Welcome back", "success");
      showApp(data.user, data);
    } catch (error) {
      el.authMessage.textContent = error.message;
    } finally {
      el.authSubmit.disabled = false;
    }
  });

  el.passwordResetRequest.addEventListener("click", async () => {
    const username = el.authUsername.value.trim();
    if (!username) {
      el.authMessage.textContent = "Enter your username first.";
      el.authUsername.focus();
      return;
    }
    el.passwordResetRequest.disabled = true;
    try {
      const data = await api("/api/auth/password-reset-request", {
        method: "POST",
        body: JSON.stringify({ username }),
      });
      el.authPassword.value = "";
      el.authMessage.textContent = data.message || "Request was sent.";
    } catch (error) {
      el.authMessage.textContent = error.message;
    } finally {
      el.passwordResetRequest.disabled = false;
    }
  });

  el.logout.addEventListener("click", async () => {
    if (!(await confirmAction("Sign out", "End the current session?", "Sign out"))) return;
    await api("/api/auth/logout", { method: "POST", body: "{}" }).catch(() => {});
    state.user = null;
    state.keys = [];
    closeAllSheets();
    setAuthMode("login");
    showView("auth");
  });

  el.search.addEventListener("input", () => {
    state.query = el.search.value;
    renderKeys();
  });
  el.sort.addEventListener("change", () => {
    state.sort = el.sort.value;
    renderKeys();
  });
  $$(".psu-segmented-control [data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      $$(".psu-segmented-control [data-filter]").forEach((candidate) => candidate.setAttribute("aria-selected", String(candidate === button)));
      renderKeys();
    });
  });

  el.rows.addEventListener("click", (event) => {
    const action = event.target.closest("[data-action]");
    const row = event.target.closest("[data-index]");
    if (!row) return;
    const index = Number(row.dataset.index);
    if (action?.dataset.action === "redeem") {
      redeem(index, action);
      return;
    }
    openDetail(index);
  });
  el.rows.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = event.target.closest("[data-index]");
    if (!row) return;
    event.preventDefault();
    openDetail(Number(row.dataset.index));
  });

  el.newKey.addEventListener("click", openNewKey);
  el.detailReveal.addEventListener("click", toggleReveal);
  el.detailCopy.addEventListener("click", copyActiveKey);
  el.detailShare.addEventListener("click", createShareLink);
  el.detailShareCopy.addEventListener("click", () => copyText(el.detailShareLink.value, "Share link copied"));
  el.detailRedeem.addEventListener("click", () => redeem(state.activeIndex, el.detailRedeem));
  el.detailUnredeem.addEventListener("click", () => unredeem(state.activeIndex, el.detailUnredeem));
  el.detailRequestReactivation.addEventListener("click", requestReactivation);
  el.detailDelete.addEventListener("click", deleteActiveKey);
  el.keyForm.addEventListener("submit", saveKey);
  el.detailGame.addEventListener("input", updateDetailLinks);

  $("#settings-sheet").addEventListener("click", settingsClick);
  $("#notifications-sheet").addEventListener("click", notificationsClick);
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-settings-mode]");
    if (!trigger) return;
    state.settingsMode = trigger.dataset.settingsMode || "account";
    closeSheet("#profile-sheet");
    loadSettings();
  });
  el.notificationsButton.addEventListener("click", loadNotifications);
  el.profileNotificationsRow.addEventListener("click", loadNotifications);

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && !views.app.hidden) {
      event.preventDefault();
      el.search.focus();
    }
  });
}

async function loadKeys() {
  el.rows.innerHTML = '<li class="keyku-empty">Loading vault...</li>';
  try {
    const data = await api("/api/keys");
    state.keys = data.keys || [];
    renderKeys();
  } catch (error) {
    el.rows.innerHTML = `<li class="keyku-empty is-error">${escapeHtml(error.message)}</li>`;
  }
}

function sortedKeys(keys) {
  const copy = keys.slice();
  const addedTime = (entry) => {
    const time = new Date(entry.addedAt || 0).getTime();
    return Number.isNaN(time) ? 0 : time;
  };
  switch (state.sort) {
    case "name-desc":
      return copy.sort((a, b) => b.game.localeCompare(a.game, "en", { sensitivity: "base", numeric: true }));
    case "added-desc":
      return copy.sort((a, b) => addedTime(b) - addedTime(a) || a.index - b.index);
    case "status-available":
      return copy.sort((a, b) => Number(a.redeemed) - Number(b.redeemed) || a.index - b.index);
    case "status-claimed":
      return copy.sort((a, b) => Number(b.redeemed) - Number(a.redeemed) || a.index - b.index);
    default:
      return copy.sort((a, b) => a.game.localeCompare(b.game, "en", { sensitivity: "base", numeric: true }));
  }
}

function renderKeys() {
  const free = state.keys.filter((entry) => !entry.redeemed).length;
  const used = state.keys.length - free;
  el.statFree.textContent = String(free);
  el.statUsed.textContent = String(used);
  el.statTotal.textContent = String(state.keys.length);

  if (!state.keys.length) {
    el.rows.innerHTML = `<li class="keyku-empty">
      <div class="psu-logo-frame" aria-hidden="true"><img src="/assets/logos/keyku.png" alt="" /></div>
      <strong>No keys yet</strong>
      <span>Admins can create keys directly in the vault.</span>
    </li>`;
    return;
  }

  let visible = sortedKeys(state.keys);
  if (state.filter === "available") visible = visible.filter((entry) => !entry.redeemed);
  if (state.filter === "claimed") visible = visible.filter((entry) => entry.redeemed);
  const query = normalize(state.query.trim());
  if (query) visible = visible.filter((entry) => normalize(entry.game).includes(query));

  if (!visible.length) {
    el.rows.innerHTML = '<li class="keyku-empty">No matching entries.</li>';
    return;
  }

  el.rows.innerHTML = visible.map((entry) => {
    const status = entry.redeemed ? "Used" : "Free";
    const statusClass = entry.redeemed ? "is-used" : "is-free";
    const redeemedBy = entry.redeemedByName ? ` by ${entry.redeemedByName}` : "";
    const meta = entry.redeemed && entry.redeemedAt
      ? `Redeemed ${formatDate(entry.redeemedAt)}${redeemedBy}`
      : (entry.addedAt ? `Added ${formatDate(entry.addedAt)}` : "Ready");
    const action = entry.redeemed
      ? '<span class="psu-button psu-button--tonal keyku-row-button">Open</span>'
      : '<button class="psu-button psu-button--filled keyku-row-button" type="button" data-action="redeem">Redeem</button>';
    return `
      <li class="keyku-key-row ${entry.redeemed ? "is-muted" : ""}" data-index="${entry.index}" tabindex="0">
        <span class="keyku-row-number">${String(entry.index + 1).padStart(2, "0")}</span>
        <span class="keyku-row-main">
          <strong>${escapeHtml(entry.game || "Untitled")}</strong>
          <small>${escapeHtml(meta)}</small>
        </span>
        <span class="keyku-secret-preview">${MASKED_KEY}</span>
        <span class="keyku-status ${statusClass}">${status}</span>
        <span class="keyku-row-actions">${action}</span>
      </li>`;
  }).join("");
}

function currentEntry() {
  return state.keys.find((entry) => entry.index === state.activeIndex);
}

function openNewKey() {
  state.creating = true;
  state.activeIndex = null;
  state.activeSecret = "";
  el.detailTitle.textContent = "New key";
  el.detailGame.value = "";
  el.detailKey.value = "";
  el.detailKey.type = "text";
  el.detailAdded.value = toDateTimeLocal(new Date().toISOString());
  el.detailRedeemed.value = "";
  el.detailRedeemedBy.value = "";
  el.detailReveal.textContent = "Hide";
  el.detailRedeem.hidden = true;
  el.detailUnredeem.hidden = true;
  el.detailDelete.hidden = true;
  el.detailRequestReactivation.hidden = true;
  el.detailShare.disabled = true;
  el.detailCopy.disabled = false;
  el.shareLinkRow.hidden = true;
  setDetailReadonly(false);
  updateDetailLinks();
  openSheet("#detail-dialog");
  el.detailGame.focus();
}

function openDetail(index) {
  const entry = state.keys.find((item) => item.index === index);
  if (!entry) return;
  state.creating = false;
  state.activeIndex = index;
  state.activeSecret = "";
  el.detailTitle.textContent = entry.game || "Key";
  el.detailGame.value = entry.game || "";
  el.detailKey.value = MASKED_KEY;
  el.detailKey.type = "password";
  el.detailAdded.value = toDateTimeLocal(entry.addedAt);
  el.detailRedeemed.value = toDateTimeLocal(entry.redeemedAt);
  el.detailRedeemedBy.value = entry.redeemedByName || (entry.redeemed ? "Unknown" : "");
  el.detailReveal.textContent = "Show";
  el.detailRedeem.hidden = entry.redeemed;
  el.detailUnredeem.hidden = !entry.redeemed;
  el.detailDelete.hidden = state.user?.role !== "admin";
  el.detailRequestReactivation.hidden = !entry.redeemed || state.user?.role === "admin";
  el.detailShare.disabled = false;
  el.detailCopy.disabled = false;
  el.shareLinkRow.hidden = true;
  setDetailReadonly(state.user?.role !== "admin");
  updateDetailLinks();
  openSheet("#detail-dialog");
}

function setDetailReadonly(readonly) {
  el.detailGame.readOnly = readonly;
  el.detailKey.readOnly = readonly;
  el.detailAdded.disabled = readonly;
  el.detailRedeemed.disabled = readonly;
  $$(".keyku-admin-field").forEach((node) => { node.hidden = state.user?.role !== "admin"; });
}

function updateDetailLinks() {
  const game = el.detailGame.value;
  el.detailTitle.textContent = game || (state.creating ? "New key" : "Key");
  el.detailSteam.href = steamSearchUrl(game);
  el.detailSteamDb.href = steamDbUrl(game);
}

async function revealActiveKey() {
  if (state.creating) {
    state.activeSecret = el.detailKey.value;
    el.detailKey.type = "text";
    el.detailReveal.textContent = "Hide";
    return state.activeSecret;
  }
  if (state.activeIndex == null) return "";
  if (!state.activeSecret) {
    const data = await api(`/api/keys/${encodeURIComponent(state.activeIndex)}/secret`);
    state.activeSecret = data.key || "";
  }
  el.detailKey.value = state.activeSecret;
  el.detailKey.type = "text";
  el.detailReveal.textContent = "Hide";
  return state.activeSecret;
}

async function toggleReveal() {
  if (el.detailKey.type === "text") {
    el.detailKey.type = "password";
    if (!state.creating) el.detailKey.value = MASKED_KEY;
    el.detailReveal.textContent = "Show";
    return;
  }
  try {
    await revealActiveKey();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function copyText(text, successMessage) {
  const value = String(text || "");
  if (!value) return false;
  try {
    await navigator.clipboard.writeText(value);
    showToast(successMessage, "success");
    return true;
  } catch (_) {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    textarea.className = "keyku-clipboard-helper";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand && document.execCommand("copy");
    textarea.remove();
    showToast(copied ? successMessage : "Copy failed", copied ? "success" : "error");
    return Boolean(copied);
  }
}

async function copyActiveKey() {
  try {
    const key = await revealActiveKey();
    await copyText(key, "Key copied");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function createShareLink() {
  if (state.activeIndex == null) return;
  el.detailShare.disabled = true;
  try {
    const data = await api(`/api/keys/${encodeURIComponent(state.activeIndex)}/share`, { method: "POST", body: "{}" });
    el.detailShareLink.value = data.shareUrl || "";
    el.shareLinkRow.hidden = false;
    el.detailShareLink.focus();
    el.detailShareLink.select();
    showToast("Share link created", "success");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    el.detailShare.disabled = false;
  }
}

async function redeem(index, button) {
  if (index == null) return;
  const target = button || el.detailRedeem;
  target.disabled = true;
  try {
    const data = await api(`/api/redeem/${encodeURIComponent(index)}`, { method: "POST", body: "{}" });
    if (data.redeemUrl) window.open(data.redeemUrl, "_blank", "noopener,noreferrer");
    showToast("Key marked as used", "success");
    await loadKeys();
    if (!el.detailDialog.hidden) openDetail(index);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    target.disabled = false;
  }
}

async function unredeem(index, button) {
  if (!(await confirmAction("Reactivate key", "Mark this key as free again?", "Reactivate"))) return;
  button.disabled = true;
  try {
    await api(`/api/unredeem/${encodeURIComponent(index)}`, { method: "POST", body: "{}" });
    showToast("Key is free again", "success");
    await loadKeys();
    openDetail(index);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function requestReactivation() {
  if (state.activeIndex == null) return;
  el.detailRequestReactivation.disabled = true;
  try {
    await api(`/api/keys/${encodeURIComponent(state.activeIndex)}/reactivation-request`, { method: "POST", body: "{}" });
    showToast("Request sent", "success");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    el.detailRequestReactivation.disabled = false;
  }
}

async function deleteActiveKey() {
  const entry = currentEntry();
  if (!(await confirmAction("Delete key", `Delete "${entry?.game || "Untitled"}" permanently?`, "Delete"))) return;
  el.detailDelete.disabled = true;
  try {
    await api(`/api/admin/keys/${encodeURIComponent(state.activeIndex)}`, { method: "DELETE" });
    showToast("Key deleted", "success");
    closeSheet("#detail-dialog");
    await loadKeys();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    el.detailDelete.disabled = false;
  }
}

async function saveKey(event) {
  event.preventDefault();
  if (state.user?.role !== "admin") return;
  el.detailSave.disabled = true;
  try {
    const body = {
      game: el.detailGame.value.trim(),
      addedAt: fromDateTimeLocal(el.detailAdded.value),
      redeemedAt: fromDateTimeLocal(el.detailRedeemed.value),
    };
    if (state.creating || state.activeSecret || el.detailKey.value !== MASKED_KEY) {
      body.key = el.detailKey.value.trim();
    }
    const path = state.creating ? "/api/admin/keys" : `/api/admin/keys/${encodeURIComponent(state.activeIndex)}`;
    const method = state.creating ? "POST" : "PATCH";
    const data = await api(path, { method, body: JSON.stringify(body) });
    showToast(state.creating ? "Key created" : "Key saved", "success");
    await loadKeys();
    openDetail(data.key.index);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    el.detailSave.disabled = false;
  }
}

async function loadNotifications() {
  if (state.user?.role !== "admin") return;
  el.notificationsBody.innerHTML = '<div class="keyku-empty">Loading notifications...</div>';
  try {
    const data = await api("/api/admin/notifications");
    updateNotificationIndicator(data.notificationCount || 0);
    renderNotifications(data);
  } catch (error) {
    el.notificationsBody.innerHTML = `<div class="keyku-empty is-error">${escapeHtml(error.message)}</div>`;
  }
}

function renderNotifications(data) {
  const pendingUsers = data.pendingUsers || [];
  const reactivations = data.reactivationRequests || [];
  const resets = data.passwordResetRequests || [];
  el.notificationsBody.innerHTML = `
    ${notificationSection("New users", pendingUsers, (user) => `
      <article class="psu-card keyku-list-card">
        <div><strong>${escapeHtml(user.username)}</strong><small>Requested ${formatDate(user.createdAt)}</small></div>
        <div class="psu-card-actions">
          <button class="psu-button psu-button--filled" data-user-approve="${escapeHtml(user.id)}" type="button">Approve</button>
          <button class="psu-button psu-button--danger" data-user-reject="${escapeHtml(user.id)}" type="button">Reject</button>
        </div>
      </article>`)}
    ${notificationSection("Reactivation", reactivations, (request) => `
      <article class="psu-card keyku-list-card">
        <div><strong>${escapeHtml(request.game || "Untitled")}</strong><small>${escapeHtml(request.requestedByName || "Unknown")} - ${formatDate(request.createdAt)}</small></div>
        <div class="psu-card-actions">
          <button class="psu-button psu-button--filled" data-reactivation-approve="${escapeHtml(request.id)}" type="button">Approve</button>
          <button class="psu-button psu-button--danger" data-reactivation-reject="${escapeHtml(request.id)}" type="button">Reject</button>
        </div>
      </article>`)}
    ${notificationSection("Password", resets, (request) => `
      <article class="psu-card keyku-list-card">
        <div><strong>${escapeHtml(request.username)}</strong><small>${formatDate(request.createdAt)}</small></div>
        <div class="keyku-inline-field">
          <input class="psu-input" type="password" minlength="10" placeholder="New password" data-reset-input="${escapeHtml(request.id)}" />
          <button class="psu-button psu-button--filled" data-reset-complete="${escapeHtml(request.id)}" type="button">Set</button>
          <button class="psu-button psu-button--danger" data-reset-reject="${escapeHtml(request.id)}" type="button">Reject</button>
        </div>
      </article>`)}
  `;
}

function notificationSection(title, items, render) {
  return `
    <section class="keyku-section-stack">
      <h3 class="keyku-section-title">${escapeHtml(title)} <span>${items.length}</span></h3>
      ${items.length ? items.map(render).join("") : '<div class="keyku-empty is-compact">No open items.</div>'}
    </section>`;
}

async function notificationsClick(event) {
  const button = event.target.closest("button");
  if (!button) return;
  const id =
    button.dataset.userApprove ||
    button.dataset.userReject ||
    button.dataset.reactivationApprove ||
    button.dataset.reactivationReject ||
    button.dataset.resetComplete ||
    button.dataset.resetReject;
  if (!id) return;
  button.disabled = true;
  try {
    let path;
    let body = "{}";
    if (button.dataset.userApprove) path = `/api/admin/users/${encodeURIComponent(id)}/approve`;
    if (button.dataset.userReject) path = `/api/admin/users/${encodeURIComponent(id)}/reject`;
    if (button.dataset.reactivationApprove) path = `/api/admin/reactivation-requests/${encodeURIComponent(id)}/approve`;
    if (button.dataset.reactivationReject) path = `/api/admin/reactivation-requests/${encodeURIComponent(id)}/reject`;
    if (button.dataset.resetComplete) {
      path = `/api/admin/password-reset-requests/${encodeURIComponent(id)}/complete`;
      body = JSON.stringify({ password: $(`[data-reset-input="${CSS.escape(id)}"]`).value });
    }
    if (button.dataset.resetReject) path = `/api/admin/password-reset-requests/${encodeURIComponent(id)}/reject`;
    await api(path, { method: "POST", body });
    showToast("Benachrichtigung aktualisiert", "success");
    await loadNotifications();
    await loadKeys();
  } catch (error) {
    showToast(error.message, "error");
    button.disabled = false;
  }
}

async function loadSettings() {
  el.settingsBody.innerHTML = '<div class="keyku-empty">Loading settings...</div>';
  try {
    if (state.settingsMode === "admin" && state.user?.role !== "admin") state.settingsMode = "account";
    if (state.settingsMode === "admin") {
      const [settings, info, users] = await Promise.all([
        api("/api/admin/settings"),
        api("/api/admin/info"),
        api("/api/admin/users"),
      ]);
      renderSettings({ settings, info, users: users.users || [] });
      return;
    }
    const info = state.settingsMode === "about"
      ? await api("/api/app/about")
      : null;
    renderSettings({ info });
  } catch (error) {
    el.settingsBody.innerHTML = `<div class="keyku-empty is-error">${escapeHtml(error.message)}</div>`;
  }
}

function renderSettings({ settings = null, info = null, users = [] } = {}) {
  el.settingsTitle.textContent = {
    account: "Account",
    appearance: "Appearance",
    about: "About",
    admin: "Admin",
  }[state.settingsMode] || "Account";
  if (state.settingsMode === "admin") {
    el.settingsBody.innerHTML = adminSettingsHtml(settings, info, users);
    return;
  }
  if (state.settingsMode === "about") {
    el.settingsBody.innerHTML = aboutSettingsHtml(info);
    return;
  }
  if (state.settingsMode === "appearance") {
    el.settingsBody.innerHTML = appearanceSettingsHtml();
    return;
  }
  el.settingsBody.innerHTML = accountSettingsHtml();
}

function accountSettingsHtml() {
  return `
    <form id="account-settings-form" class="psu-card keyku-section-stack">
      <h3 class="psu-card-title">Account settings</h3>
      <label class="psu-field">
        <span class="psu-label">Display name</span>
        <input class="psu-input" name="displayName" autocomplete="name" maxlength="80" required value="${escapeHtml(state.user?.displayName || "")}" />
      </label>
      <label class="psu-field">
        <span class="psu-label">Username</span>
        <input class="psu-input" name="username" autocomplete="username" minlength="3" maxlength="32" required value="${escapeHtml(state.user?.username || "")}" />
      </label>
      <label class="psu-field">
        <span class="psu-label">Email optional</span>
        <input class="psu-input" name="email" type="email" autocomplete="email" maxlength="180" value="${escapeHtml(state.user?.email || "")}" />
      </label>
      <label class="psu-field">
        <span class="psu-label">Current password</span>
        <input class="psu-input" name="currentPassword" type="password" autocomplete="current-password" />
      </label>
      <label class="psu-field">
        <span class="psu-label">New password optional</span>
        <input class="psu-input" name="newPassword" type="password" autocomplete="new-password" minlength="12" />
      </label>
      <label class="psu-field">
        <span class="psu-label">Repeat new password</span>
        <input class="psu-input" name="passwordConfirm" type="password" autocomplete="new-password" minlength="12" />
      </label>
      <button class="psu-button psu-button--filled" type="submit">Save account</button>
    </form>
  `;
}

function appearanceSettingsHtml() {
  const theme = document.documentElement.dataset.theme;
  const mode = document.documentElement.dataset.mode;
  return `
    <section class="psu-card keyku-section-stack">
      <h3 class="psu-card-title">Appearance</h3>
      <div class="psu-chip-group" role="group" aria-label="Choose theme">
        ${themeButton("lavender", "Lavender", theme)}
        ${themeButton("mint", "Mint", theme)}
        ${themeButton("sky", "Sky", theme)}
        ${themeButton("amber", "Amber", theme)}
        ${themeButton("rose", "Rose", theme)}
        ${themeButton("graphite", "Graphite", theme)}
      </div>
      <div class="psu-segmented-control" role="tablist" aria-label="Choose mode">
        ${modeButton("system", "System", mode)}
        ${modeButton("light", "Light", mode)}
        ${modeButton("dark", "Dark", mode)}
      </div>
    </section>
  `;
}

function aboutSettingsHtml(info) {
  return `
    <section class="psu-card keyku-identity-card">
      <div class="psu-logo-frame" aria-hidden="true"><img src="/assets/logos/keyku.png" alt="" /></div>
      <div>
        <h3 class="psu-card-title">Keyku</h3>
        <p class="psu-card-text">Key Vault</p>
      </div>
    </section>
    <section class="psu-technical-card keyku-section-stack">
      <h3 class="psu-card-title">About</h3>
      ${technicalRow("Version", info?.app?.version)}
      ${technicalRow("Build date", info?.app?.buildDate || "local")}
      ${technicalRow("Git SHA", info?.app?.gitSha || "local")}
    </section>
  `;
}

function themeButton(value, label, active) {
  return `<button class="psu-chip" type="button" data-theme-choice="${value}" aria-pressed="${String(value === active)}">${label}</button>`;
}

function modeButton(value, label, active) {
  return `<button type="button" data-mode-choice="${value}" aria-selected="${String(value === active)}">${label}</button>`;
}

function adminSettingsHtml(settings, info, users) {
  const keys = settings?.keys || {};
  const requests = settings?.requests || {};
  return `
    <section class="keyku-stat-grid">
      <article class="psu-card keyku-stat"><span>Keys</span><strong>${keys.total ?? 0}</strong></article>
      <article class="psu-card keyku-stat"><span>Free</span><strong>${keys.free ?? 0}</strong></article>
      <article class="psu-card keyku-stat"><span>Requests</span><strong>${(requests.pendingReactivations ?? 0) + (requests.pendingPasswordResets ?? 0)}</strong></article>
    </section>
    <section class="psu-card keyku-section-stack">
      <h3 class="psu-card-title">Create account</h3>
      <form id="admin-create-user-form" class="keyku-form-grid">
        <input class="psu-input" name="displayName" placeholder="Display name" required />
        <input class="psu-input" name="username" placeholder="Username" required minlength="3" maxlength="32" />
        <input class="psu-input" name="email" placeholder="Email optional" type="email" />
        <select class="psu-input" name="role"><option value="user">User</option><option value="admin">Admin</option></select>
        <input class="psu-input" name="password" placeholder="Initial password" type="password" required minlength="12" />
        <button class="psu-button psu-button--filled" type="submit">Create account</button>
      </form>
    </section>
    <section class="psu-card keyku-section-stack">
      <h3 class="psu-card-title">Accounts</h3>
      ${users.map((user) => `<article class="keyku-compact-row"><strong>${escapeHtml(user.displayName || user.username)}</strong><span>${escapeHtml(user.username)} - ${escapeHtml(user.role)}</span></article>`).join("") || '<div class="keyku-empty is-compact">No accounts.</div>'}
    </section>
    <section class="psu-card keyku-section-stack">
      <h3 class="psu-card-title">Maintenance</h3>
      <div class="psu-card-actions">
        <button class="psu-button psu-button--danger" data-maintenance="delete-used" type="button">Delete used keys</button>
        <button class="psu-button psu-button--tonal" data-maintenance="reactivate-used" type="button">Reactivate used keys</button>
        <button class="psu-button psu-button--tonal" data-maintenance="clear-resolved" type="button">Clear resolved requests</button>
      </div>
    </section>
    <section class="psu-technical-card keyku-section-stack keyku-admin-info-card">
      <h3 class="psu-card-title">Admin Info</h3>
      ${technicalRow("App", info?.app?.name)}
      ${technicalRow("Version", info?.app?.version)}
      ${technicalRow("Build", info?.app?.buildDate || "local")}
      ${technicalRow("Git SHA", info?.app?.gitSha || "local")}
      ${technicalRow("Data", info?.runtime?.dataDir)}
      ${technicalRow("CSV", info?.runtime?.csvPath)}
      ${technicalRow("Setup", info?.health?.setup?.setupCompleted ? "completed" : "pending")}
      ${technicalRow("Health", info?.health?.status)}
      ${technicalRow("Log Level", info?.runtime?.logLevel)}
      <button class="psu-button psu-button--outlined" data-copy-admin-info type="button">Copy debug details</button>
    </section>`;
}

function technicalRow(label, value) {
  return `<div class="keyku-tech-row"><span>${escapeHtml(label)}</span><code class="psu-technical-value">${escapeHtml(value || "-")}</code></div>`;
}

async function settingsClick(event) {
  const theme = event.target.closest("[data-theme-choice]");
  const mode = event.target.closest("[data-mode-choice]");
  const maintenance = event.target.closest("[data-maintenance]");
  const copyAdmin = event.target.closest("[data-copy-admin-info]");
  if (theme) {
    setPixelSoftUtilityTheme(theme.dataset.themeChoice);
    await loadSettings();
    return;
  }
  if (mode) {
    setPixelSoftUtilityMode(mode.dataset.modeChoice);
    await loadSettings();
    return;
  }
  if (copyAdmin) {
    await copyText(el.settingsBody.querySelector(".keyku-admin-info-card")?.innerText || "", "Debug details copied");
    return;
  }
  if (maintenance) {
    const action = maintenance.dataset.maintenance;
    const messages = {
      "delete-used": "Permanently delete all used keys?",
      "reactivate-used": "Mark all used keys as free again?",
      "clear-resolved": "Clear all resolved requests?",
    };
    if (!(await confirmAction("Maintenance", messages[action], "Run"))) return;
    const paths = {
      "delete-used": "/api/admin/maintenance/delete-used-keys",
      "reactivate-used": "/api/admin/maintenance/reactivate-used-keys",
      "clear-resolved": "/api/admin/maintenance/clear-resolved-requests",
    };
    await api(paths[action], { method: "POST", body: "{}" });
    showToast("Maintenance completed", "success");
    await loadSettings();
    await loadKeys();
  }
}

document.addEventListener("submit", async (event) => {
  const accountForm = event.target.closest("#account-settings-form");
  if (accountForm) {
    event.preventDefault();
    const button = accountForm.querySelector("button[type='submit']");
    button.disabled = true;
    const data = new FormData(accountForm);
    try {
      const result = await api("/api/account", {
        method: "PATCH",
        body: JSON.stringify({
          displayName: data.get("displayName"),
          username: data.get("username"),
          email: data.get("email"),
          currentPassword: data.get("currentPassword"),
          newPassword: data.get("newPassword"),
          passwordConfirm: data.get("passwordConfirm"),
        }),
      });
      state.user = result.user;
      const userInitials = initials(result.user);
      el.profileButton.textContent = userInitials;
      el.profileAvatar.textContent = userInitials;
      el.profileName.textContent = result.user.displayName || result.user.username;
      el.profileId.textContent = `${result.user.username}${result.user.role === "admin" ? " - Admin" : ""}`;
      state.settingsMode = "account";
      await loadSettings();
      showToast("Account saved", "success");
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      button.disabled = false;
    }
    return;
  }

  const form = event.target.closest("#admin-create-user-form");
  if (!form) return;
  event.preventDefault();
  const button = form.querySelector("button[type='submit']");
  button.disabled = true;
  const data = new FormData(form);
  try {
    await api("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        displayName: data.get("displayName"),
        username: data.get("username"),
        email: data.get("email"),
        role: data.get("role"),
        password: data.get("password"),
      }),
    });
    form.reset();
    showToast("Account created", "success");
    await loadSettings();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
  }
});

function openSheet(selector) {
  const sheet = $(selector);
  if (!sheet) return;
  sheet.hidden = false;
  sheet.querySelector("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")?.focus();
}

function closeSheet(selector) {
  const sheet = $(selector);
  if (sheet) sheet.hidden = true;
}

function closeAllSheets() {
  $$(".psu-backdrop:not([hidden])").forEach((sheet) => { sheet.hidden = true; });
}

function confirmAction(title, message, confirmLabel = "Run") {
  return new Promise((resolve) => {
    el.confirmTitle.textContent = title;
    el.confirmMessage.textContent = message;
    el.confirmOk.textContent = confirmLabel;
    el.confirmDialog.hidden = false;
    el.confirmCancel.focus();
    const cleanup = (value) => {
      el.confirmDialog.hidden = true;
      el.confirmCancel.removeEventListener("click", onCancel);
      el.confirmOk.removeEventListener("click", onOk);
      el.confirmDialog.removeEventListener("click", onBackdrop);
      resolve(value);
    };
    const onCancel = () => cleanup(false);
    const onOk = () => cleanup(true);
    const onBackdrop = (event) => {
      if (event.target === el.confirmDialog) cleanup(false);
    };
    el.confirmCancel.addEventListener("click", onCancel);
    el.confirmOk.addEventListener("click", onOk);
    el.confirmDialog.addEventListener("click", onBackdrop);
  });
}

bootstrap().catch((error) => {
  console.error(error);
  showToast("Keyku could not start", "error");
});
