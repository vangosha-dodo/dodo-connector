#!/usr/bin/env node
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const config = {
  chrome: process.env.DODO_AUTH_CHROME_PATH || '/home/ubuntu/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome',
  secretDir: process.env.DODO_AUTH_SECRET_DIR || '/home/ubuntu/.openclaw/secret',
  tmpDir: process.env.DODO_AUTH_TMP_DIR || '/home/ubuntu/.openclaw/workspace/tmp',
  officeUrl: process.env.DODO_AUTH_OFFICE_URL || 'https://officemanager.dodois.io/OfficeManager/EmployeeList',
  adminUrl: process.env.DODO_AUTH_ADMIN_URL || 'https://admin.dodois.io/Infrastructure/Authenticate/Structure',
  credentialFile: process.env.DODO_AUTH_CREDENTIAL_FILE || 'officemanager.json',
  pendingFile: process.env.DODO_AUTH_PENDING_FILE || 'officemanager_mfa_pending.json',
  officeFiles: (process.env.DODO_AUTH_OFFICE_FILES || 'officemanager_session.json,officemanager_app_session.json,officemanager_session_checked.json')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean),
  adminFile: process.env.DODO_AUTH_ADMIN_FILE || 'admin_dodois_session.json',
};

const dodoDomains = [
  'officemanager.dodois.io',
  'admin.dodois.io',
  'auth.dodois.io',
  'analytics.dodois.io',
  '.dodois.io',
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function secretPath(filename) {
  if (path.isAbsolute(filename)) return filename;
  return path.join(config.secretDir, filename);
}

async function readJson(file) {
  return JSON.parse(await fs.readFile(file, 'utf8'));
}

async function writeJson600(file, value) {
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, `${JSON.stringify(value, null, 2)}\n`);
  await fs.chmod(file, 0o600).catch(() => null);
}

async function waitForJson(url, timeoutMs = 15000) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      const text = await response.text();
      if (response.ok) return JSON.parse(text);
      lastError = new Error(`${response.status} ${text.slice(0, 200)}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(250);
  }
  throw lastError || new Error(`Timed out waiting for ${url}`);
}

async function connectCdp(webSocketDebuggerUrl) {
  const ws = new WebSocket(webSocketDebuggerUrl);
  const pending = new Map();
  let nextId = 1;
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(JSON.stringify(message.error)));
    else resolve(message.result);
  };
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });
  return {
    send(method, params = {}) {
      const id = nextId++;
      ws.send(JSON.stringify({ id, method, params }));
      return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
    },
    close() {
      ws.close();
    },
  };
}

async function startBrowser() {
  const port = 16000 + Math.floor(Math.random() * 3000);
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'dodo-bridge-auth-'));
  const child = spawn(config.chrome, [
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    'about:blank',
  ], { stdio: 'ignore' });
  child.unref();
  await waitForJson(`http://127.0.0.1:${port}/json/version`);
  const targets = await waitForJson(`http://127.0.0.1:${port}/json/list`);
  const target = targets.find((item) => item.type === 'page');
  if (!target) throw new Error('Chrome page target not found');
  return { child, profile, target };
}

async function stopBrowser(browser) {
  try {
    browser.child.kill('SIGTERM');
  } catch {}
  await fs.rm(browser.profile, { recursive: true, force: true }).catch(() => null);
}

async function withBrowser(callback) {
  const browser = await startBrowser();
  const cdp = await connectCdp(browser.target.webSocketDebuggerUrl);
  try {
    await cdp.send('Network.enable');
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    return await callback(cdp);
  } finally {
    cdp.close();
    await stopBrowser(browser);
  }
}

async function evaluate(cdp, expression) {
  const result = await cdp.send('Runtime.evaluate', { expression, returnByValue: true });
  return result.result.value;
}

async function pageInfo(cdp) {
  return evaluate(cdp, `(() => {
    const text = document.body ? document.body.innerText : '';
    return {
      href: location.href,
      host: location.host,
      path: location.pathname,
      title: document.title,
      text: text.slice(0, 1000).replace(/\\s+/g, ' ').trim()
    };
  })()`);
}

function sessionCookies(session) {
  if (!session || typeof session !== 'object') return {};
  if (session.cookies && typeof session.cookies === 'object') return session.cookies;
  const cookies = {};
  for (const [name, value] of Object.entries(session)) {
    if (typeof value === 'string') cookies[name] = value;
  }
  return cookies;
}

async function setCookies(cdp, cookies) {
  for (const [name, value] of Object.entries(cookies || {})) {
    if (typeof value !== 'string' || value.length === 0) continue;
    for (const domain of dodoDomains) {
      await cdp.send('Network.setCookie', {
        name,
        value,
        domain,
        path: '/',
        secure: true,
        httpOnly: !name.startsWith('SelectedLanguage'),
        sameSite: 'None',
      }).catch(() => null);
    }
  }
}

async function getDodoCookies(cdp) {
  const all = await cdp.send('Network.getAllCookies');
  const result = {};
  for (const cookie of all.cookies || []) {
    if (cookie.domain && cookie.domain.includes('dodois.io')) {
      result[cookie.name] = cookie.value;
    }
  }
  return result;
}

function isLogin(info) {
  const haystack = `${info.host}\n${info.path}\n${info.title}\n${info.text}`;
  return /auth\.dodois\.io/i.test(info.host)
    || /\/Auth\/Login/i.test(info.path)
    || /sign in|login|войти|авторизац/i.test(haystack);
}

function isMfa(info) {
  const haystack = `${info.path}\n${info.title}\n${info.text}`;
  return /mfa|two.?factor|verification|one.?time|код|почт|email|подтверж/i.test(haystack);
}

function officeOk(info) {
  return info.host === 'officemanager.dodois.io'
    && info.path === '/OfficeManager/EmployeeList'
    && /Все сотрудники|Менеджер офиса|EmployeeList|OfficeManager/i.test(`${info.title}\n${info.text}`);
}

function adminOk(info) {
  return info.host === 'admin.dodois.io'
    && info.path === '/Infrastructure/Authenticate/Structure'
    && !isLogin(info)
    && !isMfa(info);
}

async function nudgePage(cdp) {
  return evaluate(cdp, `(() => {
    const hidden = document.forms.hiddenform || document.querySelector('form[name="hiddenform"]');
    if (hidden) {
      hidden.submit();
      return 'hiddenform';
    }
    if (location.pathname === '/Infrastructure/Authenticate/SelectRole') {
      const item = [...document.querySelectorAll('a[href], button, input[type="submit"]')]
        .find((el) => /Менеджер офиса|OfficeManager|Тамбов/i.test(el.innerText || el.value || el.href || ''));
      if (item) {
        item.click();
        return 'select-role';
      }
    }
    return '';
  })()`);
}

async function navigateAndSettle(cdp, url, okPredicate, timeoutMs = 45000) {
  await cdp.send('Page.navigate', { url });
  const started = Date.now();
  let last = null;
  while (Date.now() - started < timeoutMs) {
    await sleep(1000);
    const info = await pageInfo(cdp);
    last = info;
    if (okPredicate(info) || isMfa(info)) return info;
    const action = await nudgePage(cdp);
    if (action) await sleep(2500);
  }
  return last || pageInfo(cdp);
}

async function fillLogin(cdp, username, password) {
  return evaluate(cdp, `(() => {
    const setValue = (el, value) => {
      if (!el) return false;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(el, value);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    };
    const inputs = [...document.querySelectorAll('input')];
    const userInput = inputs.find((el) => /email|login|user/i.test([el.name, el.id, el.autocomplete, el.placeholder].join(' ')))
      || inputs.find((el) => ['email', 'text'].includes((el.type || '').toLowerCase()));
    const passwordInput = inputs.find((el) => (el.type || '').toLowerCase() === 'password');
    const changedUser = setValue(userInput, ${JSON.stringify(username)});
    const changedPassword = setValue(passwordInput, ${JSON.stringify(password)});
    const submit = document.querySelector('button[type="submit"], input[type="submit"]')
      || [...document.querySelectorAll('button')].find((el) => /sign|log|войти|продолж/i.test(el.innerText || el.value || ''));
    if (submit) submit.click();
    return { changedUser, changedPassword, submitted: Boolean(submit) };
  })()`);
}

async function fillMfaCode(cdp, code) {
  return evaluate(cdp, `(() => {
    const inputs = [...document.querySelectorAll('input')];
    const input = inputs.find((el) => /code|mfa|otp|tfa|verification|confirm/i.test([el.name, el.id, el.autocomplete, el.placeholder].join(' ')))
      || inputs.find((el) => ['text', 'tel', 'number'].includes((el.type || '').toLowerCase()));
    if (!input) return { submitted: false, reason: 'code_input_not_found' };
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(input, ${JSON.stringify(code)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    const operation = document.querySelector('input[name="Operation"]');
    if (operation) setter.call(operation, 'confirm');
    const form = input.form || document.querySelector('form#tfa-form') || document.querySelector('form');
    const submit = form?.querySelector('button[type="submit"], input[type="submit"]')
      || [...document.querySelectorAll('button, input[type="submit"]')].find((el) => /confirm|submit|continue|подтверд|продолж/i.test(el.innerText || el.value || ''));
    if (submit) submit.click();
    else if (form) form.submit();
    return { submitted: Boolean(submit || form) };
  })()`);
}

function publicInfo(info) {
  if (!info) return null;
  return {
    host: info.host,
    path: info.path,
    title: info.title,
    office_ok: officeOk(info),
    admin_ok: adminOk(info),
    login_required: isLogin(info),
    mfa_required: isMfa(info),
  };
}

async function checkSessionFile(filename, targetUrl, okPredicate) {
  const file = secretPath(filename);
  try {
    const session = await readJson(file);
    return withBrowser(async (cdp) => {
      await setCookies(cdp, sessionCookies(session));
      const info = await navigateAndSettle(cdp, targetUrl, okPredicate, 35000);
      return { file: filename, exists: true, ok: okPredicate(info), ...publicInfo(info) };
    });
  } catch (error) {
    return { file: filename, exists: false, ok: false, error: error.message };
  }
}

async function status() {
  const office = [];
  for (const filename of config.officeFiles) {
    office.push(await checkSessionFile(filename, config.officeUrl, officeOk));
  }
  const admin = await checkSessionFile(config.adminFile, config.adminUrl, adminOk);
  const pendingExists = await fs.access(secretPath(config.pendingFile)).then(() => true).catch(() => false);
  return {
    ok: office.some((item) => item.ok) && admin.ok,
    office,
    admin,
    mfa_pending: pendingExists,
  };
}

async function saveSessions(cdp, info) {
  const cookies = await getDodoCookies(cdp);
  const now = Math.floor(Date.now() / 1000);
  const updatedFiles = [];
  if (officeOk(info)) {
    const officeSession = {
      created_at: now,
      current_url: config.officeUrl,
      cookies,
      note: 'OfficeManager app session refreshed by dodo-bridge. Do not print or commit.',
    };
    for (const filename of config.officeFiles) {
      await writeJson600(secretPath(filename), officeSession);
      updatedFiles.push(filename);
    }
  }
  const adminInfo = await navigateAndSettle(cdp, config.adminUrl, adminOk, 35000);
  if (adminOk(adminInfo)) {
    const adminCookies = await getDodoCookies(cdp);
    await writeJson600(secretPath(config.adminFile), adminCookies);
    updatedFiles.push(config.adminFile);
  }
  return { updated_files: updatedFiles, admin: publicInfo(adminInfo) };
}

async function savePending(cdp, info) {
  const pending = {
    created_at: Math.floor(Date.now() / 1000),
    current_url: info.href,
    cookies: await getDodoCookies(cdp),
    note: 'Pending Dodo IS MFA context. Submit a fresh code to this context; do not start a new login.',
  };
  await writeJson600(secretPath(config.pendingFile), pending);
}

async function refresh() {
  const before = await status();
  if (before.ok) return { ok: true, already_authorized: true, before };

  const credentials = await readJson(secretPath(config.credentialFile));
  const username = credentials.username || credentials.login || credentials.email;
  const password = credentials.password || credentials.pass;
  if (!username || !password) throw new Error('Credential file must contain username/password');

  return withBrowser(async (cdp) => {
    let info = await navigateAndSettle(cdp, credentials.url || config.officeUrl, (item) => officeOk(item) || adminOk(item), 45000);
    if (isLogin(info)) {
      const login = await fillLogin(cdp, username, password);
      await sleep(3500);
      info = await navigateAndSettle(cdp, config.officeUrl, officeOk, 45000);
      if (!login.changedUser || !login.changedPassword) {
        return { ok: false, error: 'login_form_not_filled', login, final: publicInfo(info) };
      }
    }
    if (isMfa(info)) {
      await savePending(cdp, info);
      return { ok: false, mfa_required: true, pending_saved: true, final: publicInfo(info) };
    }
    if (!officeOk(info) && !adminOk(info)) {
      return { ok: false, error: 'authorization_did_not_reach_known_page', final: publicInfo(info) };
    }
    const saved = await saveSessions(cdp, info);
    return { ok: true, mfa_required: false, final: publicInfo(info), ...saved };
  });
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8').trim();
}

async function submitCode() {
  const code = (process.env.DODO_AUTH_MFA_CODE || await readStdin()).trim();
  if (!/^\d{6}$/.test(code)) throw new Error('MFA code must be exactly 6 digits');
  const pending = await readJson(secretPath(config.pendingFile));
  return withBrowser(async (cdp) => {
    await setCookies(cdp, sessionCookies(pending));
    await cdp.send('Page.navigate', { url: pending.current_url || config.officeUrl });
    await sleep(2500);
    const submit = await fillMfaCode(cdp, code);
    await sleep(3500);
    let info = await navigateAndSettle(cdp, config.officeUrl, officeOk, 45000);
    if (isMfa(info)) {
      await savePending(cdp, info);
      return { ok: false, mfa_required: true, pending_saved: true, submit, final: publicInfo(info) };
    }
    if (!officeOk(info)) {
      return { ok: false, error: 'mfa_submit_did_not_reach_office', submit, final: publicInfo(info) };
    }
    const saved = await saveSessions(cdp, info);
    await fs.rm(secretPath(config.pendingFile), { force: true }).catch(() => null);
    return { ok: true, mfa_required: false, pending_cleared: true, submit, final: publicInfo(info), ...saved };
  });
}

async function main() {
  const action = process.argv[2] || process.env.DODO_AUTH_BRIDGE_ACTION || 'status';
  let result;
  if (action === 'status') result = await status();
  else if (action === 'refresh') result = await refresh();
  else if (action === 'submit-code') result = await submitCode();
  else throw new Error(`Unknown action: ${action}`);
  console.log(JSON.stringify({ action, ...result }, null, 2));
}

main().catch((error) => {
  console.log(JSON.stringify({ ok: false, error: error.message }, null, 2));
  process.exit(1);
});

