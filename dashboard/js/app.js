// Entry point: load the encrypted bundle, unlock it with the viewer's password, render the tabs.
import { WrongPasswordError, decryptBundle } from "./crypto.js";
import { formatDate, formatDateTime } from "./format.js";
import { renderGuide, renderNotices, renderResults, renderToday, renderTrend } from "./views.js";

const PASSWORD_KEY = "trader-dashboard-password";
const THEME_KEY = "trader-dashboard-theme";
const VIEWS = { today: renderToday, results: renderResults, trend: renderTrend, guide: renderGuide };

const $ = (selector) => document.querySelector(selector);

const storage = {
  get: (key) => {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set: (key, value) => {
    try {
      localStorage.setItem(key, value);
    } catch {
      // private mode or blocked storage: the page still works, it just does not remember
    }
  },
  remove: (key) => {
    try {
      localStorage.removeItem(key);
    } catch {
      // nothing stored
    }
  },
};

/**
 * Where the bundle lives. On GitHub Pages it is read from the main branch directly, so the page never waits for
 * a Pages rebuild after the daily scan commits new data. `?data=` accepts a same-origin path for testing only:
 * the browser resolves it (so "\\host" tricks are seen as the other host they are) and any other origin is ignored.
 */
function bundleUrl() {
  const override = new URLSearchParams(location.search).get("data");
  if (override) {
    const url = new URL(override, location.href);
    if (url.origin === location.origin) return url.href;
  }
  if (location.hostname.endsWith(".github.io")) {
    const owner = location.hostname.split(".")[0];
    const repo = location.pathname.split("/").filter(Boolean)[0];
    if (repo) return `https://raw.githubusercontent.com/${owner}/${repo}/main/dashboard/data/dashboard.enc`;
  }
  return "data/dashboard.enc";
}

function setStatus(text, { error = false } = {}) {
  const status = $("#unlock-status");
  status.textContent = text;
  status.classList.toggle("unlock__status--error", error);
}

function selectTab(name, { focus = false } = {}) {
  const key = name in VIEWS ? name : "today";
  for (const tab of document.querySelectorAll('[role="tab"]')) {
    const selected = tab.id === `tab-${key}`;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus();
    $(`#${tab.getAttribute("aria-controls")}`).hidden = !selected;
  }
  if (location.hash !== `#${key}`) history.replaceState(null, "", `#${key}`);
}

function setUpTabs() {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  for (const tab of tabs) {
    tab.addEventListener("click", () => selectTab(tab.id.replace("tab-", "")));
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      const next = tabs[(tabs.indexOf(tab) + step + tabs.length) % tabs.length];
      selectTab(next.id.replace("tab-", ""), { focus: true });
    });
  }
  window.addEventListener("hashchange", () => selectTab(location.hash.slice(1)));
}

function show(bundle) {
  $("#unlock").hidden = true;
  $("#tabs").hidden = false;
  $("#lock").hidden = false;
  $("#data-date").textContent =
    `${formatDate(bundle.latest_price_date, { year: true })}の終値まで ・ 更新 ${formatDateTime(bundle.generated_at)}`;
  renderNotices(bundle, $("#notices"));
  for (const [name, render] of Object.entries(VIEWS)) render(bundle, $(`#view-${name}`));
  selectTab(location.hash.slice(1));
}

async function unlock(envelope, password, remember) {
  setStatus("開いています…");
  let bundle;
  try {
    bundle = await decryptBundle(envelope, password);
  } catch (error) {
    if (error instanceof WrongPasswordError) {
      storage.remove(PASSWORD_KEY);
      setStatus("パスワードが違います。", { error: true });
    } else {
      // Not the password: keep any saved one, and say what failed (an old browser, or a damaged download).
      setStatus(`開けませんでした（${error.message}）。最新の Chrome・Safari・Edge で開き直してください。`, { error: true });
    }
    return false;
  }
  if (remember) storage.set(PASSWORD_KEY, password);
  setStatus("");
  show(bundle);
  return true;
}

function setUpTheme() {
  const button = $("#theme-toggle");
  const isDark = () =>
    document.documentElement.dataset.theme === "dark" ||
    (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  const label = () => {
    button.textContent = isDark() ? "明るい表示にする" : "暗い表示にする";
  };
  button.addEventListener("click", () => {
    const theme = isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    storage.set(THEME_KEY, theme);
    label();
  });
  label();
}

async function main() {
  setUpTheme();
  setUpTabs();
  $("#lock").addEventListener("click", () => {
    storage.remove(PASSWORD_KEY);
    location.reload();
  });

  let envelope;
  try {
    const response = await fetch(bundleUrl(), { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    envelope = await response.text();
  } catch (error) {
    setStatus(
      `データを読み込めませんでした（${error.message}）。日次スキャンでまだ作られていないか、通信できない状態です。`,
      { error: true },
    );
    return;
  }

  const form = $("#unlock-form");
  const submit = $("#unlock-submit");
  submit.disabled = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    const opened = await unlock(envelope, $("#password").value, $("#remember").checked);
    submit.disabled = opened;
  });

  const saved = storage.get(PASSWORD_KEY);
  if (saved) {
    $("#remember").checked = true;
    await unlock(envelope, saved, true);
  }
}

main();
