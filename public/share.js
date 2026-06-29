import { initPixelSoftUtilityTheme } from "./design-system/theme-controller.js";

const token = decodeURIComponent(window.location.pathname.split("/").filter(Boolean).pop() || "");
const title = document.querySelector("#share-title");
const meta = document.querySelector("#share-meta");
const keyBox = document.querySelector("#share-key");
const copyButton = document.querySelector("#share-copy-key");
const redeemLink = document.querySelector("#share-redeem");
const steamLink = document.querySelector("#share-steam");
const steamDbLink = document.querySelector("#share-steamdb");
const errorBox = document.querySelector("#share-error");
const toast = document.querySelector("#toast");

let sharedKey = "";

initPixelSoftUtilityTheme({ appId: "keyku", defaultTheme: "lavender", defaultMode: "system" });
loadIconSprite();
loadShare();

async function loadIconSprite() {
  try {
    document.querySelector("#icon-sprite").innerHTML = await fetch("/icons/psu-icons.svg", { cache: "force-cache" }).then((response) => response.text());
  } catch (_) {
    document.querySelector("#icon-sprite").innerHTML = "";
  }
}

function showToast(message, kind = "default") {
  toast.textContent = message;
  toast.className = `keyku-toast is-visible ${kind === "error" ? "is-error" : ""} ${kind === "success" ? "is-success" : ""}`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("is-visible"), 3000);
}

function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" });
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    showToast("Key copied", "success");
  } catch (_) {
    showToast(text, "success");
  }
}

async function loadShare() {
  try {
    const response = await fetch(`/api/share/${encodeURIComponent(token)}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Share link not found");
    sharedKey = data.key;
    title.textContent = data.game || "Steam-Key";
    meta.textContent = data.redeemed && data.redeemedAt
      ? `Redeemed on ${formatDate(data.redeemedAt)}`
      : "Public key link";
    keyBox.textContent = data.key;
    redeemLink.href = data.redeemUrl;
    steamLink.href = data.steamUrl;
    steamDbLink.href = data.steamDbUrl;
  } catch (error) {
    title.textContent = "Invalid share link";
    meta.textContent = "Keyku - Key Vault";
    keyBox.textContent = "Not found";
    errorBox.textContent = error.message;
    copyButton.disabled = true;
    [redeemLink, steamLink, steamDbLink].forEach((link) => {
      link.removeAttribute("href");
      link.setAttribute("aria-disabled", "true");
    });
  }
}

copyButton.addEventListener("click", () => {
  if (sharedKey) copy(sharedKey);
});
