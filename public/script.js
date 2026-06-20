const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const authView = $("#auth-view");
const appView = $("#app-view");
const authForm = $("#auth-form");
const authTitle = $("#auth-title");
const authCopy = $("#auth-copy");
const authUsername = $("#auth-username");
const authPassword = $("#auth-password");
const authSubmit = $("#auth-submit");
const authSwitch = $("#auth-switch");
const authMessage = $("#auth-message");
const passwordResetRequest = $("#password-reset-request");

const rows = $("#rows");
const heroSub = $("#hero-sub");
const toast = $("#toast");
const search = $("#search");
const sort = $("#sort");
const userPill = $("#user-pill");
const logoutBtn = $("#logout");
const newKeyBtn = $("#new-key");
const adminOpen = $("#admin-open");
const pendingBadge = $("#pending-badge");
const notificationDot = $("#notification-dot");
const themeToggle = $("#theme-toggle");
const settingsOpen = $("#settings-open");
const adminPanel = $("#admin-panel");
const adminUsers = $("#admin-users");
const settingsPanel = $("#settings-panel");
const settingsBody = $("#settings-body");
const segButtons = $$(".seg-btn");
const counts = {
  all: $('[data-count="all"]'),
  available: $('[data-count="available"]'),
  claimed: $('[data-count="claimed"]'),
};

const detailPanel = $("#detail-panel");
const keyForm = $("#key-form");
const detailStatus = $("#detail-status");
const detailTitle = $("#detail-title");
const detailGame = $("#detail-game");
const detailKey = $("#detail-key");
const detailAdded = $("#detail-added");
const detailRedeemed = $("#detail-redeemed");
const detailReveal = $("#detail-reveal");
const detailRedeem = $("#detail-redeem");
const detailShare = $("#detail-share");
const detailCopy = $("#detail-copy");
const detailRequestReactivation = $("#detail-request-reactivation");
const shareLinkRow = $("#share-link-row");
const detailShareLink = $("#detail-share-link");
const detailShareCopy = $("#detail-share-copy");
const detailSteam = $("#detail-steam");
const detailSteamDb = $("#detail-steamdb");
const detailSave = $("#detail-save");
const detailUnredeem = $("#detail-unredeem");
const detailDelete = $("#detail-delete");

const requiredElements = {
  authView,
  appView,
  authForm,
  authSwitch,
  passwordResetRequest,
  rows,
  heroSub,
  search,
  sort,
  notificationDot,
  themeToggle,
  settingsOpen,
  settingsPanel,
  settingsBody,
  detailPanel,
  keyForm,
  detailShareLink,
  detailShareCopy,
};

const missingElements = Object.entries(requiredElements)
  .filter(([, element]) => !element)
  .map(([name]) => name);

if (missingElements.length) {
  document.body.insertAdjacentHTML("beforeend", `
    <main class="auth-shell">
      <section class="auth-panel">
        <div class="brand brand-auth"><img class="brand-logo" src="/logo.svg?v=20260620-1" alt="" /><span>Steam Key Vault</span></div>
        <p class="auth-kicker">Frontend files out of sync</p>
        <h1>Please reload</h1>
        <p class="auth-copy">HTML and JavaScript are out of sync. Clear the browser cache or restart the container.</p>
        <p class="auth-message">Missing elements: ${missingElements.map(escapeHtml).join(", ")}</p>
      </section>
    </main>
  `);
  throw new Error(`Frontend DOM mismatch: ${missingElements.join(", ")}`);
}

let authMode = "login";
let currentUser = null;
let allKeys = [];
let filterQuery = "";
let statusFilter = "all";
let sortMode = "name-asc";
let pendingCount = 0;
let activeIndex = null;
let activeSecret = "";
let isCreating = false;
const themeStorageKey = "steam-key-vault-theme";

function preferredTheme() {
  const stored = localStorage.getItem(themeStorageKey);
  if (stored === "light" || stored === "dark") return stored;
  return "dark";
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(themeStorageKey, theme);
  themeToggle.setAttribute("aria-label", theme === "light" ? "Enable dark mode" : "Enable light mode");
  themeToggle.title = theme === "light" ? "Enable dark mode" : "Enable light mode";
}

function updateNotificationIndicator(count) {
  pendingCount = Number(count || 0);
  const show = currentUser?.role === "admin" && pendingCount > 0;
  pendingBadge.hidden = !show;
  notificationDot.hidden = !show;
  pendingBadge.textContent = String(pendingCount);
}

function showToast(message, kind = "default") {
  toast.textContent = message;
  toast.className = `toast is-visible ${kind === "error" ? "is-error" : ""} ${kind === "success" ? "is-success" : ""}`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("is-visible"), 3000);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function normalize(value) {
  return String(value).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
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
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await readJsonResponse(response);
  if (response.status === 401 && path !== "/api/auth/me") {
    await showAuth();
    throw new Error(data.error || "Login required");
  }
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function setAuthMode(nextMode) {
  authMode = nextMode;
  const isRegister = authMode === "register";
  authTitle.textContent = isRegister ? "Register" : "Sign in";
  authCopy.textContent = isRegister
    ? "The first user becomes admin. After that, admins must approve new registrations."
    : "Sign in to access the shared key vault.";
  authSubmit.textContent = isRegister ? "Submit registration" : "Sign in";
  authSwitch.textContent = isRegister ? "Already approved? Sign in" : "Need access? Register";
  passwordResetRequest.hidden = isRegister;
  authPassword.autocomplete = isRegister ? "new-password" : "current-password";
  authMessage.textContent = "";
}

async function showAuth(message = "") {
  currentUser = null;
  appView.hidden = true;
  authView.hidden = false;
  closeDetail();
  if (message) authMessage.textContent = message;
}

function showApp(user, meta = {}) {
  currentUser = user;
  pendingCount = Number(meta.notificationCount || meta.pendingCount || 0);
  authView.hidden = true;
  appView.hidden = false;
  userPill.textContent = `${user.username}${user.role === "admin" ? " - Admin" : ""}`;
  adminOpen.hidden = user.role !== "admin";
  settingsOpen.hidden = user.role !== "admin";
  newKeyBtn.hidden = user.role !== "admin";
  updateNotificationIndicator(pendingCount);
}

async function initAuth() {
  try {
    const data = await api("/api/auth/me");
    if (data.authenticated) {
      showApp(data.user, data);
      await loadKeys();
    } else {
      showAuth();
    }
  } catch (error) {
    console.error(error);
    showAuth("Server is unreachable.");
  }
}

authSwitch.addEventListener("click", () => {
  setAuthMode(authMode === "login" ? "register" : "login");
});

passwordResetRequest.addEventListener("click", async () => {
  const username = authUsername.value.trim();
  if (!username) {
    authMessage.textContent = "Enter a username first.";
    authUsername.focus();
    return;
  }
  passwordResetRequest.disabled = true;
  authMessage.textContent = "";
  try {
    const data = await api("/api/auth/password-reset-request", {
      method: "POST",
      body: JSON.stringify({ username }),
    });
    authPassword.value = "";
    authMessage.textContent = data.message || "Request sent to the admin.";
  } catch (error) {
    authMessage.textContent = error.message;
  } finally {
    passwordResetRequest.disabled = false;
  }
});

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authSubmit.disabled = true;
  authMessage.textContent = "";
  try {
    const endpoint = authMode === "register" ? "/api/auth/register" : "/api/auth/login";
    const data = await api(endpoint, {
      method: "POST",
      body: JSON.stringify({
        username: authUsername.value,
        password: authPassword.value,
      }),
    });
    if (data.authenticated || data.user?.status === "approved") {
      showApp(data.user, data);
      authForm.reset();
      await loadKeys();
      showToast(authMode === "register" ? "Admin account created" : "Welcome back", "success");
    } else {
      setAuthMode("login");
      authMessage.textContent = data.message || "Registration saved. Please wait for approval.";
      authPassword.value = "";
    }
  } catch (error) {
    authMessage.textContent = error.message;
  } finally {
    authSubmit.disabled = false;
  }
});

logoutBtn.addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
  } catch (_) {
    // Logout should still clear the local view.
  }
  allKeys = [];
  showAuth();
});

function sortedKeys(keys) {
  const copy = keys.slice();
  const addedTime = (entry) => {
    const time = new Date(entry.addedAt || 0).getTime();
    return Number.isNaN(time) ? 0 : time;
  };
  switch (sortMode) {
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
  const available = allKeys.filter((entry) => !entry.redeemed).length;
  const claimed = allKeys.length - available;
  heroSub.textContent = `${available} free - ${claimed} used - ${allKeys.length} total`;
  counts.all.textContent = String(allKeys.length);
  counts.available.textContent = String(available);
  counts.claimed.textContent = String(claimed);

  if (!allKeys.length) {
    rows.innerHTML = '<li class="placeholder">The shared vault is empty. Add keys in <code>data/keys.csv</code> or create them here as an admin.</li>';
    return;
  }

  let visible = sortedKeys(allKeys);
  if (statusFilter === "available") visible = visible.filter((entry) => !entry.redeemed);
  if (statusFilter === "claimed") visible = visible.filter((entry) => entry.redeemed);

  const query = normalize(filterQuery.trim());
  if (query) visible = visible.filter((entry) => normalize(entry.game).includes(query));

  if (!visible.length) {
    rows.innerHTML = '<li class="placeholder">No matching entries found.</li>';
    return;
  }

  rows.innerHTML = visible.map((entry) => {
    const status = entry.redeemed ? "Used" : "Free";
    const statusClass = entry.redeemed ? "is-claimed" : "is-free";
    const dateLine = entry.redeemed && entry.redeemedAt
      ? `redeemed ${formatDate(entry.redeemedAt)}`
      : (entry.addedAt ? `added ${formatDate(entry.addedAt)}` : "");
    const action = entry.redeemed
      ? `<button class="btn btn-muted" type="button" data-open="${entry.index}">Open</button>`
      : `<button class="btn btn-primary" type="button" data-redeem="${entry.index}">Redeem</button>`;

    return `
      <li class="row ${entry.redeemed ? "row-claimed" : ""}" data-row-index="${entry.index}" tabindex="0">
        <span class="row-index">${String(entry.index + 1).padStart(2, "0")}</span>
        <span class="row-game">
          <strong>${escapeHtml(entry.game || "Untitled")}</strong>
          ${dateLine ? `<small>${escapeHtml(dateLine)}</small>` : ""}
        </span>
        <span class="row-key" aria-label="Key hidden">*****-*****-*****</span>
        <span class="status ${statusClass}">${status}</span>
        <span class="row-actions">${action}</span>
      </li>
    `;
  }).join("");
}

async function loadKeys() {
  rows.innerHTML = '<li class="placeholder">Loading vault...</li>';
  try {
    const data = await api("/api/keys");
    allKeys = data.keys || [];
    renderKeys();
  } catch (error) {
    console.error(error);
    rows.innerHTML = `<li class="placeholder error">${escapeHtml(error.message || "Vault is unreachable")}</li>`;
  }
}

async function redeem(index, button) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = "Opening...";
  try {
    const data = await api(`/api/redeem/${encodeURIComponent(index)}`, { method: "POST", body: "{}" });
    if (data.redeemUrl) window.open(data.redeemUrl, "_blank", "noopener,noreferrer");
    showToast("Key marked as used and Steam opened", "success");
    await loadKeys();
    if (!detailPanel.hidden && activeIndex === index) openDetail(index);
  } catch (error) {
    showToast(error.message || "Redeem failed", "error");
    button.disabled = false;
    button.textContent = original;
  }
}

async function unredeem(index, button) {
  if (!window.confirm("Mark this key as free again?")) return;
  button.disabled = true;
  const original = button.textContent;
  button.textContent = "Saving...";
  try {
    await api(`/api/unredeem/${encodeURIComponent(index)}`, { method: "POST", body: "{}" });
    showToast("Key is free again", "success");
    await loadKeys();
    openDetail(index);
  } catch (error) {
    showToast(error.message || "Reactivate failed", "error");
    button.disabled = false;
    button.textContent = original;
  }
}

async function revealActiveKey() {
  if (isCreating) {
    detailKey.type = detailKey.type === "password" ? "text" : "password";
    detailReveal.textContent = detailKey.type === "password" ? "Reveal" : "Hide";
    return detailKey.value;
  }
  if (activeIndex == null) return "";
  if (!activeSecret) {
    const data = await api(`/api/keys/${encodeURIComponent(activeIndex)}/secret`);
    activeSecret = data.key || "";
    detailKey.value = activeSecret;
  }
  detailKey.type = "text";
  detailReveal.textContent = "Hide";
  detailCopy.disabled = !activeSecret;
  return activeSecret;
}

function currentEntry() {
  return allKeys.find((entry) => entry.index === activeIndex);
}

function setDetailReadonly(readonly) {
  detailGame.readOnly = readonly;
  detailKey.readOnly = readonly;
  detailAdded.disabled = readonly;
  detailRedeemed.disabled = readonly;
  $$(".admin-only-field, .admin-edit-actions").forEach((element) => {
    element.hidden = !currentUser || currentUser.role !== "admin";
  });
}

function openNewKey() {
  isCreating = true;
  activeIndex = null;
  activeSecret = "";
  detailStatus.textContent = "New entry";
  detailTitle.textContent = "New key";
  detailGame.value = "";
  detailKey.value = "";
  detailKey.type = "text";
  detailAdded.value = toDateTimeLocal(new Date().toISOString());
  detailRedeemed.value = "";
  detailRedeem.hidden = true;
  detailUnredeem.hidden = true;
  detailDelete.hidden = true;
  detailRequestReactivation.hidden = true;
  detailShare.disabled = true;
  detailCopy.disabled = false;
  shareLinkRow.hidden = true;
  detailShareLink.value = "";
  detailReveal.textContent = "Hide";
  detailSteam.href = steamSearchUrl("");
  detailSteamDb.href = steamDbUrl("");
  setDetailReadonly(false);
  detailPanel.hidden = false;
  detailGame.focus();
}

function openDetail(index) {
  const entry = allKeys.find((candidate) => candidate.index === index);
  if (!entry) return;
  isCreating = false;
  activeIndex = index;
  activeSecret = "";
  detailStatus.textContent = entry.redeemed ? "Used" : "Free";
  detailTitle.textContent = entry.game || "Untitled";
  detailGame.value = entry.game || "";
  detailKey.value = "*****-*****-*****";
  detailKey.type = "password";
  detailAdded.value = toDateTimeLocal(entry.addedAt);
  detailRedeemed.value = toDateTimeLocal(entry.redeemedAt);
  detailReveal.textContent = "Reveal";
  detailRedeem.hidden = entry.redeemed;
  detailUnredeem.hidden = !entry.redeemed;
  detailDelete.hidden = currentUser?.role !== "admin";
  detailRequestReactivation.hidden = !entry.redeemed || currentUser?.role === "admin";
  detailShare.disabled = false;
  detailCopy.disabled = false;
  shareLinkRow.hidden = true;
  detailShareLink.value = "";
  detailSteam.href = steamSearchUrl(entry.game);
  detailSteamDb.href = steamDbUrl(entry.game);
  setDetailReadonly(currentUser?.role !== "admin");
  detailPanel.hidden = false;
}

function closeDetail() {
  activeIndex = null;
  activeSecret = "";
  isCreating = false;
  detailPanel.hidden = true;
}

async function copyText(text, successMessage) {
  const value = String(text || "");
  if (!value) return false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
    } else {
      throw new Error("Clipboard API unavailable");
    }
    showToast(successMessage, "success");
    return true;
  } catch (_) {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    textarea.style.top = "0";
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    const copied = document.execCommand && document.execCommand("copy");
    textarea.remove();
    showToast(copied ? successMessage : "Copy failed: select the text manually.", copied ? "success" : "error");
    return Boolean(copied);
  }
}

rows.addEventListener("click", (event) => {
  const redeemButton = event.target.closest("[data-redeem]");
  if (redeemButton) {
    event.stopPropagation();
    redeem(Number.parseInt(redeemButton.dataset.redeem, 10), redeemButton);
    return;
  }
  const openButton = event.target.closest("[data-open]");
  if (openButton) {
    event.stopPropagation();
    openDetail(Number.parseInt(openButton.dataset.open, 10));
    return;
  }
  const row = event.target.closest("[data-row-index]");
  if (row) openDetail(Number.parseInt(row.dataset.rowIndex, 10));
});

rows.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest("[data-row-index]");
  if (!row) return;
  event.preventDefault();
  openDetail(Number.parseInt(row.dataset.rowIndex, 10));
});

detailPanel.addEventListener("click", (event) => {
  if (event.target.closest("[data-detail-close]")) closeDetail();
});

detailReveal.addEventListener("click", async () => {
  if (detailKey.type === "text" && !isCreating) {
    detailKey.type = "password";
    detailKey.value = "*****-*****-*****";
    detailReveal.textContent = "Reveal";
    return;
  }
  if (detailKey.type === "text" && isCreating) {
    detailKey.type = "password";
    detailReveal.textContent = "Reveal";
    return;
  }
  try {
    await revealActiveKey();
  } catch (error) {
    showToast(error.message || "Could not reveal key", "error");
  }
});

detailCopy.addEventListener("click", async () => {
  try {
    const key = await revealActiveKey();
    if (key) await copyText(key, "Key copied");
  } catch (error) {
    showToast(error.message || "Copy failed", "error");
  }
});

detailShare.addEventListener("click", async () => {
  if (activeIndex == null) return;
  detailShare.disabled = true;
  try {
    const data = await api(`/api/keys/${encodeURIComponent(activeIndex)}/share`, { method: "POST", body: "{}" });
    detailShareLink.value = data.shareUrl || "";
    shareLinkRow.hidden = false;
    detailShareLink.focus();
    detailShareLink.select();
    showToast("Share link created", "success");
  } catch (error) {
    showToast(error.message || "Share link failed", "error");
  } finally {
    detailShare.disabled = false;
  }
});

detailShareCopy.addEventListener("click", async () => {
  await copyText(detailShareLink.value, "Share link copied");
});

detailRedeem.addEventListener("click", () => {
  if (activeIndex == null) return;
  redeem(activeIndex, detailRedeem);
});

detailUnredeem.addEventListener("click", () => {
  if (activeIndex == null) return;
  unredeem(activeIndex, detailUnredeem);
});

detailRequestReactivation.addEventListener("click", async () => {
  if (activeIndex == null) return;
  detailRequestReactivation.disabled = true;
  try {
    await api(`/api/keys/${encodeURIComponent(activeIndex)}/reactivation-request`, { method: "POST", body: "{}" });
    showToast("Reactivation request sent to the admin", "success");
  } catch (error) {
    showToast(error.message || "Request failed", "error");
  } finally {
    detailRequestReactivation.disabled = false;
  }
});

detailDelete.addEventListener("click", async () => {
  if (activeIndex == null) return;
  const entry = currentEntry();
  if (!window.confirm(`Delete entry "${entry?.game || "Untitled"}" permanently?`)) return;
  detailDelete.disabled = true;
  try {
    await api(`/api/admin/keys/${encodeURIComponent(activeIndex)}`, { method: "DELETE" });
    showToast("Entry deleted", "success");
    closeDetail();
    await loadKeys();
  } catch (error) {
    showToast(error.message || "Delete failed", "error");
  } finally {
    detailDelete.disabled = false;
  }
});

keyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (currentUser?.role !== "admin") return;
  detailSave.disabled = true;
  try {
    const body = {
      game: detailGame.value.trim(),
      addedAt: fromDateTimeLocal(detailAdded.value),
      redeemedAt: fromDateTimeLocal(detailRedeemed.value),
    };
    if (isCreating || activeSecret || detailKey.value !== "*****-*****-*****") {
      body.key = detailKey.value.trim();
    }
    const path = isCreating ? "/api/admin/keys" : `/api/admin/keys/${encodeURIComponent(activeIndex)}`;
    const method = isCreating ? "POST" : "PATCH";
    const data = await api(path, { method, body: JSON.stringify(body) });
    showToast(isCreating ? "Entry created" : "Entry saved", "success");
    await loadKeys();
    openDetail(data.key.index);
  } catch (error) {
    showToast(error.message || "Save failed", "error");
  } finally {
    detailSave.disabled = false;
  }
});

detailGame.addEventListener("input", () => {
  const game = detailGame.value;
  detailTitle.textContent = game || (isCreating ? "New key" : "Entry");
  detailSteam.href = steamSearchUrl(game);
  detailSteamDb.href = steamDbUrl(game);
});

newKeyBtn.addEventListener("click", openNewKey);

themeToggle.addEventListener("click", () => {
  const current = document.documentElement.dataset.theme === "light" ? "light" : "dark";
  setTheme(current === "light" ? "dark" : "light");
});

function metric(label, value) {
  return `
    <div class="metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderSettings(data) {
  const keys = data.keys || {};
  const users = data.users || {};
  const requests = data.requests || {};
  settingsBody.innerHTML = `
    <section class="settings-section">
      <h3>Vault</h3>
      <div class="metric-grid">
        ${metric("All", keys.total ?? 0)}
        ${metric("Free", keys.free ?? 0)}
        ${metric("Used", keys.used ?? 0)}
      </div>
    </section>
    <section class="settings-section">
      <h3>Users</h3>
      <div class="metric-grid">
        ${metric("Total", users.total ?? 0)}
        ${metric("Approved", users.approved ?? 0)}
        ${metric("Pending", users.pending ?? 0)}
      </div>
    </section>
    <section class="settings-section">
      <h3>Requests</h3>
      <div class="metric-grid">
        ${metric("Reactivation", requests.pendingReactivations ?? 0)}
        ${metric("Password reset", requests.pendingPasswordResets ?? 0)}
        ${metric("Resolved", (requests.resolvedReactivations ?? 0) + (requests.resolvedPasswordResets ?? 0))}
      </div>
    </section>
    <section class="settings-section danger-zone">
      <h3>Maintenance</h3>
      <div class="settings-actions">
        <button class="btn btn-danger" type="button" data-setting-action="delete-used">Delete used keys</button>
        <button class="btn btn-muted" type="button" data-setting-action="reactivate-used">Reactivate used keys</button>
        <button class="btn btn-muted" type="button" data-setting-action="clear-resolved">Clear resolved requests</button>
      </div>
    </section>
  `;
}

async function loadAdminSettings() {
  settingsBody.innerHTML = '<div class="placeholder">Loading settings...</div>';
  try {
    const data = await api("/api/admin/settings");
    renderSettings(data);
  } catch (error) {
    settingsBody.innerHTML = `<div class="placeholder error">${escapeHtml(error.message)}</div>`;
  }
}

settingsOpen.addEventListener("click", async () => {
  settingsPanel.hidden = false;
  await loadAdminSettings();
});

settingsPanel.addEventListener("click", async (event) => {
  if (event.target.closest("[data-settings-close]")) {
    settingsPanel.hidden = true;
    return;
  }
  const actionButton = event.target.closest("[data-setting-action]");
  if (!actionButton) return;
  const action = actionButton.dataset.settingAction;
  const messages = {
    "delete-used": "Permanently delete all used keys?",
    "reactivate-used": "Mark all used keys as free again?",
    "clear-resolved": "Clear all resolved requests from history?",
  };
  if (!window.confirm(messages[action] || "Run this action?")) return;
  const paths = {
    "delete-used": "/api/admin/maintenance/delete-used-keys",
    "reactivate-used": "/api/admin/maintenance/reactivate-used-keys",
    "clear-resolved": "/api/admin/maintenance/clear-resolved-requests",
  };
  actionButton.disabled = true;
  try {
    const result = await api(paths[action], { method: "POST", body: "{}" });
    if (result.summary) renderSettings(result.summary);
    await loadKeys();
    showToast("Settings updated", "success");
  } catch (error) {
    showToast(error.message || "Action failed", "error");
  } finally {
    actionButton.disabled = false;
  }
});

search.addEventListener("input", (event) => {
  filterQuery = event.target.value;
  renderKeys();
});

sort.addEventListener("change", (event) => {
  sortMode = event.target.value;
  renderKeys();
});

segButtons.forEach((button) => {
  button.addEventListener("click", () => {
    statusFilter = button.dataset.filter;
    segButtons.forEach((candidate) => candidate.classList.toggle("is-active", candidate === button));
    renderKeys();
  });
});

function emptyNotice(text) {
  return `<div class="placeholder compact">${escapeHtml(text)}</div>`;
}

function renderNotifications(data) {
  const pendingUsers = data.pendingUsers || [];
  const reactivationRequests = data.reactivationRequests || [];
  const passwordResetRequests = data.passwordResetRequests || [];

  const pendingUserHtml = pendingUsers.length ? pendingUsers.map((user) => `
    <li class="admin-user">
      <div>
        <strong>${escapeHtml(user.username)}</strong>
        <small>${escapeHtml(user.role)} - registered ${formatDate(user.createdAt)}</small>
      </div>
      <div class="admin-actions">
        <button class="btn btn-primary" type="button" data-approve="${user.id}">Approve</button>
        <button class="btn btn-danger" type="button" data-reject="${user.id}">Reject</button>
      </div>
    </li>
  `).join("") : emptyNotice("No new user registrations.");

  const requestHtml = reactivationRequests.length ? reactivationRequests.map((request) => `
    <li class="admin-user">
      <div>
        <strong>${escapeHtml(request.game || "Untitled key")}</strong>
        <small>requested by ${escapeHtml(request.requestedByName || "unknown")} - ${formatDate(request.createdAt)}</small>
      </div>
      <div class="admin-actions">
        <button class="btn btn-primary" type="button" data-reactivation-approve="${request.id}">Approve</button>
        <button class="btn btn-danger" type="button" data-reactivation-reject="${request.id}">Reject</button>
      </div>
    </li>
  `).join("") : emptyNotice("No pending reactivation requests.");

  const passwordResetHtml = passwordResetRequests.length ? passwordResetRequests.map((request) => `
    <li class="admin-user admin-user-reset">
      <div>
        <strong>${escapeHtml(request.username)}</strong>
        <small>requested ${formatDate(request.createdAt)}</small>
      </div>
      <div class="password-reset-row">
        <input type="password" placeholder="New password" minlength="10" data-password-input="${request.id}" />
        <button class="btn btn-primary" type="button" data-password-complete="${request.id}">Set</button>
        <button class="btn btn-danger" type="button" data-password-reject="${request.id}">Reject</button>
      </div>
    </li>
  `).join("") : emptyNotice("No pending password reset requests.");

  adminUsers.innerHTML = `
    <section class="notification-section">
      <h3>New users <span>${pendingUsers.length}</span></h3>
      <ul>${pendingUserHtml}</ul>
    </section>
    <section class="notification-section">
      <h3>Reactivation requests <span>${reactivationRequests.length}</span></h3>
      <ul>${requestHtml}</ul>
    </section>
    <section class="notification-section">
      <h3>Password reset <span>${passwordResetRequests.length}</span></h3>
      <ul>${passwordResetHtml}</ul>
    </section>
  `;
}

async function loadNotifications() {
  adminUsers.innerHTML = '<div class="placeholder">Loading notifications...</div>';
  try {
    const data = await api("/api/admin/notifications");
    renderNotifications(data);
    updateNotificationIndicator(data.notificationCount || 0);
  } catch (error) {
    adminUsers.innerHTML = `<div class="placeholder error">${escapeHtml(error.message)}</div>`;
  }
}

adminOpen.addEventListener("click", async () => {
  adminPanel.hidden = false;
  await loadNotifications();
});

adminPanel.addEventListener("click", async (event) => {
  if (event.target.closest("[data-modal-close]")) {
    adminPanel.hidden = true;
    return;
  }
  const approve = event.target.closest("[data-approve]");
  const reject = event.target.closest("[data-reject]");
  const reactApprove = event.target.closest("[data-reactivation-approve]");
  const reactReject = event.target.closest("[data-reactivation-reject]");
  const passwordComplete = event.target.closest("[data-password-complete]");
  const passwordReject = event.target.closest("[data-password-reject]");
  const target = approve || reject || reactApprove || reactReject || passwordComplete || passwordReject;
  if (!target) return;
  target.disabled = true;
  try {
    if (passwordComplete || passwordReject) {
      const requestId = passwordComplete?.dataset.passwordComplete || passwordReject.dataset.passwordReject;
      const input = adminPanel.querySelector(`[data-password-input="${requestId}"]`);
      const password = input ? input.value : "";
      const path = passwordComplete
        ? `/api/admin/password-reset-requests/${encodeURIComponent(requestId)}/complete`
        : `/api/admin/password-reset-requests/${encodeURIComponent(requestId)}/reject`;
      await api(path, {
        method: "POST",
        body: passwordComplete ? JSON.stringify({ password }) : "{}",
      });
      if (input) input.value = "";
      showToast(passwordComplete ? "Password has been reset" : "Password reset request rejected", "success");
    } else {
      const path = approve
        ? `/api/admin/users/${encodeURIComponent(approve.dataset.approve)}/approve`
        : reject
          ? `/api/admin/users/${encodeURIComponent(reject.dataset.reject)}/reject`
          : reactApprove
            ? `/api/admin/reactivation-requests/${encodeURIComponent(reactApprove.dataset.reactivationApprove)}/approve`
            : `/api/admin/reactivation-requests/${encodeURIComponent(reactReject.dataset.reactivationReject)}/reject`;
      await api(path, { method: "POST", body: "{}" });
      showToast(approve || reactApprove ? "Approved" : "Rejected", "success");
      if (reactApprove) await loadKeys();
    }
    await loadNotifications();
  } catch (error) {
    showToast(error.message, "error");
    target.disabled = false;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (!detailPanel.hidden) closeDetail();
    if (!adminPanel.hidden) adminPanel.hidden = true;
    if (!settingsPanel.hidden) settingsPanel.hidden = true;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && !appView.hidden) {
    event.preventDefault();
    search.focus();
  }
});

setTheme(preferredTheme());
setAuthMode("login");
initAuth();
