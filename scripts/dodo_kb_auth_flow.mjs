#!/usr/bin/env node
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import tls from 'node:tls';

const config = {
  chrome: process.env.DODO_KB_AUTH_CHROME_PATH
    || process.env.DODO_AUTH_CHROME_PATH
    || '/home/ubuntu/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome',
  secretDir: process.env.DODO_AUTH_SECRET_DIR || '/home/ubuntu/.openclaw/secret',
  tmpDir: process.env.DODO_AUTH_TMP_DIR || '/home/ubuntu/.openclaw/workspace/tmp',
  credentialFile: process.env.DODO_KB_AUTH_CREDENTIAL_FILE
    || process.env.DODO_AUTH_CREDENTIAL_FILE
    || 'officemanager.json',
  mailAuthFile: process.env.DODO_KB_AUTH_MAIL_AUTH_FILE || '/home/ubuntu/.openclaw/dodo/mail.ru_auth.json',
  sessionFile: process.env.DODO_KB_AUTH_SESSION_FILE || 'knowledgebase_session.json',
  baseUrl: (process.env.DODO_KB_BASE_URL || 'https://dodopizza.info').replace(/\/+$/, ''),
};

const target = new URL(config.baseUrl);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function secretPath(filename) {
  return path.isAbsolute(filename) ? filename : path.join(config.secretDir, filename);
}

async function readJson(filename) {
  return JSON.parse(await fs.readFile(secretPath(filename), 'utf8'));
}

async function writeJson600(filename, payload) {
  const file = secretPath(filename);
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, JSON.stringify(payload, null, 2) + '\n');
  await fs.chmod(file, 0o600);
}

function imapQuote(value) {
  return `"${String(value).replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"`;
}

function imapDate(date) {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${date.getUTCDate()}-${months[date.getUTCMonth()]}-${date.getUTCFullYear()}`;
}

async function imapConnect() {
  const auth = JSON.parse(await fs.readFile(config.mailAuthFile, 'utf8'));
  const socket = tls.connect({ host: auth.server, port: 993, servername: auth.server });
  socket.setEncoding('utf8');
  let buffer = '';
  const waiters = [];
  socket.on('data', (chunk) => {
    buffer += chunk;
    for (const waiter of [...waiters]) waiter();
  });
  socket.on('error', (error) => {
    for (const waiter of [...waiters]) waiter(error);
  });

  async function waitFor(predicate, timeoutMs = 30000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (predicate(buffer)) return buffer;
      await new Promise((resolve, reject) => {
        const waiter = (error) => {
          const index = waiters.indexOf(waiter);
          if (index >= 0) waiters.splice(index, 1);
          error ? reject(error) : resolve();
        };
        waiters.push(waiter);
        setTimeout(waiter, 250);
      });
    }
    throw new Error('IMAP timeout');
  }

  await waitFor((text) => /^\* OK/m.test(text));
  let tagNo = 1;
  async function command(commandText) {
    const tag = `A${tagNo++}`;
    buffer = '';
    socket.write(`${tag} ${commandText}\r\n`);
    const response = await waitFor((text) => new RegExp(`^${tag} (OK|NO|BAD)`, 'm').test(text));
    if (!new RegExp(`^${tag} OK`, 'm').test(response)) {
      throw new Error(`IMAP command failed: ${commandText.split(' ')[0]}`);
    }
    return response;
  }
  return { auth, socket, command };
}

function parseDodoCode(subject) {
  return subject.match(/DodoIS confirmation code:\s*(\d{6})/i)?.[1]
    || subject.match(/Код подтверждения DodoIS:\s*(\d{6})/i)?.[1]
    || null;
}

async function listDodoConfirmationHeaders() {
  const imap = await imapConnect();
  try {
    await imap.command(`LOGIN ${imapQuote(imap.auth.login)} ${imapQuote(imap.auth.pass)}`);
    const since = imapDate(new Date(Date.now() - 2 * 24 * 60 * 60 * 1000));
    const folders = ['INBOX', 'Spam', '&BCEEPwQwBDw-'];
    const result = [];
    for (const folder of folders) {
      try {
        await imap.command(`SELECT ${folder}`);
        const searchResponse = await imap.command(
          `SEARCH FROM ${imapQuote('noreply@dodopizza.com')} SINCE ${since}`,
        );
        const idsLine = searchResponse.split(/\r?\n/).find((line) => line.startsWith('* SEARCH')) || '';
        const ids = (idsLine.match(/\d+/g) || []).map(Number).sort((a, b) => a - b);
        for (const id of ids.slice(-20)) {
          const header = await imap.command(`FETCH ${id} RFC822.HEADER`);
          const unfolded = header.replace(/\r?\n[ \t]+/g, ' ');
          const subject = unfolded.match(/^Subject:\s*(.*)$/im)?.[1] || '';
          const dateRaw = unfolded.match(/^Date:\s*(.*)$/im)?.[1] || '';
          const date = dateRaw ? new Date(dateRaw) : new Date();
          const code = parseDodoCode(subject);
          if (code) result.push({ id, code, date: date.toISOString(), source: 'subject', folder });
        }
      } catch {
        // Some folders may not exist in every mailbox.
      }
    }
    return result.sort((a, b) => a.id - b.id);
  } finally {
    try {
      await imap.command('LOGOUT');
    } catch {}
    imap.socket.destroy();
  }
}

async function waitForNewDodoCode(afterId, timeoutMs = 90000) {
  const started = Date.now();
  let lastSeenId = afterId;
  while (Date.now() - started < timeoutMs) {
    const messages = await listDodoConfirmationHeaders();
    const newer = messages.filter((item) => item.id > afterId).sort((a, b) => b.id - a.id);
    if (newer[0]) return newer[0];
    if (messages.at(-1)) lastSeenId = Math.max(lastSeenId, messages.at(-1).id);
    await sleep(2500);
  }
  throw new Error(`No fresh Dodo confirmation email after id ${afterId}; last seen ${lastSeenId}`);
}

async function waitJson(url, timeoutMs = 15000) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      const text = await response.text();
      if (response.ok) return JSON.parse(text);
      lastError = new Error(`${response.status} ${text.slice(0, 300)}`);
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
    const item = pending.get(message.id);
    pending.delete(message.id);
    message.error ? item.reject(new Error(JSON.stringify(message.error))) : item.resolve(message.result);
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
  const port = 10650 + Math.floor(Math.random() * 500);
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'dodo-kb-auth-'));
  const child = spawn(config.chrome, [
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    'about:blank',
  ], { stdio: 'ignore' });
  child.unref();
  await waitJson(`http://127.0.0.1:${port}/json/version`);
  const targets = await waitJson(`http://127.0.0.1:${port}/json/list`);
  const page = targets.find((item) => item.type === 'page');
  if (!page) throw new Error('Chrome page target not found');
  return { child, profile, page };
}

async function stopBrowser(browser) {
  try {
    browser.child.kill('SIGTERM');
  } catch {}
  await fs.rm(browser.profile, { recursive: true, force: true }).catch(() => null);
}

async function evaluate(cdp, expression) {
  const result = await cdp.send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'Runtime.evaluate failed');
  return result.result.value;
}

async function pageInfo(cdp) {
  return evaluate(cdp, `(() => {
    const url = new URL(window.location.href);
    return {
      href: window.location.href,
      host: url.host,
      path: url.pathname,
      title: document.title || '',
      text: (document.body?.innerText || '').replace(/\\s+/g, ' ').slice(0, 800)
    };
  })()`);
}

function publicInfo(info) {
  if (!info) return null;
  return {
    host: info.host,
    path: info.path,
    title: info.title,
    kb_ok: kbOk(info),
    login_required: isLogin(info),
    mfa_required: isMfa(info),
  };
}

function kbOk(info) {
  if (!info) return false;
  const text = `${info.title}\n${info.text}`;
  return info.host === target.host
    && !info.path.includes('/Auth/Login')
    && !/status code:\s*401|unauthorized|sign in|login|continue with google/i.test(text);
}

function isLogin(info) {
  if (!info) return false;
  const text = `${info.href}\n${info.title}\n${info.text}`;
  return /auth\.dodois\.io\/login\/password|sign in to tracker|password|парол/i.test(text);
}

function isMfa(info) {
  if (!info) return false;
  const text = `${info.href}\n${info.title}\n${info.text}`;
  return /auth\.dodois\.io\/mfa\/login\/email|mfa|one.?time|код|почт|email|подтверж/i.test(text);
}

async function waitUntil(cdp, predicate, timeoutMs = 50000) {
  const started = Date.now();
  let last = await pageInfo(cdp);
  while (Date.now() - started < timeoutMs) {
    last = await pageInfo(cdp);
    if (predicate(last)) return last;
    await sleep(1000);
  }
  return last;
}

function sessionCookies(session) {
  const source = session?.cookies || session || {};
  if (Array.isArray(source)) {
    return Object.fromEntries(
      source
        .filter((item) => item?.name && item?.value)
        .map((item) => [item.name, item.value]),
    );
  }
  return source;
}

async function setCookies(cdp, cookiesByName) {
  const domains = [
    target.host,
    'knowledgebase.dodois.io',
    'auth.dodois.io',
    'officemanager.dodois.io',
    '.dodois.io',
  ];
  for (const [name, value] of Object.entries(cookiesByName || {})) {
    for (const domain of domains) {
      await cdp.send('Network.setCookie', {
        name,
        value,
        domain,
        path: '/',
        secure: true,
        httpOnly: !String(name).startsWith('SelectedLanguage'),
        sameSite: 'None',
      }).catch(() => null);
    }
  }
}

async function getRelevantCookies(cdp) {
  const { cookies } = await cdp.send('Network.getAllCookies');
  const result = {};
  for (const cookie of cookies || []) {
    const domain = String(cookie.domain || '');
    if (domain.includes(target.host) || domain.includes('dodois.io')) {
      result[cookie.name] = cookie.value;
    }
  }
  return result;
}

async function clickDodoProvider(cdp, timeoutMs = 30000) {
  const started = Date.now();
  let last = null;
  while (Date.now() - started < timeoutMs) {
    last = await evaluate(cdp, `(() => {
      const provider = document.querySelector('a[data-testid="login_dodois"]')
        || Array.from(document.querySelectorAll('a, button')).find((item) => /Dodo IS/i.test(item.innerText || item.value || ''));
      if (provider) {
        provider.click();
        return { clicked: true, readyState: document.readyState };
      }
      return {
        clicked: false,
        readyState: document.readyState,
        link_count: document.querySelectorAll('a, button').length,
      };
    })()`);
    if (last.clicked) return last;
    await sleep(500);
  }
  return last || { clicked: false };
}

async function submitCredentials(cdp, username, password) {
  return evaluate(cdp, `(() => {
    const inputs = Array.from(document.querySelectorAll('input'));
    const userInput = inputs.find((el) => /email|login|user/i.test([el.name, el.id, el.autocomplete, el.placeholder].join(' ')))
      || inputs.find((el) => ['email', 'text'].includes((el.type || '').toLowerCase()));
    const passInput = inputs.find((el) => (el.type || '').toLowerCase() === 'password');
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    if (userInput) {
      setter.call(userInput, ${JSON.stringify(username)});
      userInput.dispatchEvent(new Event('input', { bubbles: true }));
      userInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (passInput) {
      setter.call(passInput, ${JSON.stringify(password)});
      passInput.dispatchEvent(new Event('input', { bubbles: true }));
      passInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
    const form = passInput?.form || userInput?.form || document.querySelector('form');
    const submit = form?.querySelector('button[type="submit"], input[type="submit"]')
      || Array.from(document.querySelectorAll('button, input[type="submit"]')).find((el) => /sign|login|войти|продолж/i.test(el.innerText || el.value || ''));
    if (form?.requestSubmit) form.requestSubmit(submit || undefined);
    else if (submit) submit.click();
    else if (form) form.submit();
    return { changedUser: Boolean(userInput), changedPassword: Boolean(passInput), submitted: Boolean(submit || form) };
  })()`);
}

async function clickSendEmailAgain(cdp) {
  return evaluate(cdp, `(() => {
    const form = document.querySelector('form#tfa-form') || document.querySelector('form');
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    let op = form?.querySelector('input[name="Operation"]');
    if (!op && form) {
      op = document.createElement('input');
      op.type = 'hidden';
      op.name = 'Operation';
      form.appendChild(op);
    }
    if (op) setter.call(op, 'refresh');
    const submit = form?.querySelector('button[name="Operation"][value="refresh"], input[type="submit"][name="Operation"][value="refresh"]')
      || Array.from(document.querySelectorAll('button, input[type="submit"], a')).find((el) => /again|resend|refresh|повтор|ещ. раз|отправ/i.test(el.innerText || el.value || ''));
    if (form?.requestSubmit) form.requestSubmit(submit || undefined);
    else if (submit) submit.click();
    else if (form) form.submit();
    return { submitted: Boolean(submit || form) };
  })()`);
}

async function submitMfa(cdp, code) {
  return evaluate(cdp, `(() => {
    const inputs = Array.from(document.querySelectorAll('input'));
    const input = inputs.find((el) => /code|mfa|otp|tfa|verification|confirm/i.test([el.name, el.id, el.autocomplete, el.placeholder].join(' ')))
      || inputs.find((el) => ['text', 'tel', 'number'].includes((el.type || '').toLowerCase()));
    const form = input?.form || document.querySelector('form');
    if (!input || !form) return { submitted: false, changed: false };
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(input, ${JSON.stringify(code)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    let op = form.querySelector('input[name="Operation"]');
    if (!op) {
      op = document.createElement('input');
      op.type = 'hidden';
      op.name = 'Operation';
      form.appendChild(op);
    }
    setter.call(op, 'confirm');
    const submitter = form.querySelector('button[name="Operation"][value="confirm"], input[type="submit"][name="Operation"][value="confirm"]')
      || Array.from(form.querySelectorAll('button, input[type="submit"]')).find((el) => /confirm|подтверд|продолж|войти/i.test(el.innerText || el.value || ''));
    if (form.requestSubmit) form.requestSubmit(submitter || undefined);
    else if (submitter) submitter.click();
    else form.submit();
    return { submitted: true, changed: true };
  })()`);
}

async function withBrowser(callback) {
  const browser = await startBrowser();
  const cdp = await connectCdp(browser.page.webSocketDebuggerUrl);
  try {
    await cdp.send('Network.enable');
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    return await callback(cdp);
  } finally {
    try {
      cdp.close();
    } catch {}
    await stopBrowser(browser);
  }
}

async function status() {
  const sessionFile = secretPath(config.sessionFile);
  let session;
  try {
    session = JSON.parse(await fs.readFile(sessionFile, 'utf8'));
  } catch (error) {
    return {
      ok: false,
      session_file: config.sessionFile,
      exists: false,
      error: error.code === 'ENOENT' ? 'KB session file is missing' : error.message,
    };
  }

  return withBrowser(async (cdp) => {
    await setCookies(cdp, sessionCookies(session));
    await cdp.send('Page.navigate', { url: config.baseUrl + '/' });
    const info = await waitUntil(cdp, (item) => kbOk(item) || isLogin(item) || isMfa(item), 25000);
    return {
      ok: kbOk(info),
      session_file: config.sessionFile,
      exists: true,
      final: publicInfo(info),
      saved_at: session.savedAt || session.created_at || null,
    };
  });
}

async function refresh() {
  const current = await status().catch((error) => ({ ok: false, error: error.message }));
  if (current.ok) return { ok: true, already_authorized: true, before: current };

  const credentials = await readJson(config.credentialFile);
  const username = credentials.username || credentials.login || credentials.email;
  const password = credentials.password || credentials.pass;
  if (!username || !password) throw new Error('Credential file must contain username/password');

  const baselineMessages = await listDodoConfirmationHeaders();
  const baselineId = baselineMessages.at(-1)?.id || 0;

  return withBrowser(async (cdp) => {
    const loginUrl = `${config.baseUrl}/Auth/Login?ReturnUrl=%2F`;
    await cdp.send('Page.navigate', { url: loginUrl });
    let info = await waitUntil(cdp, (item) => kbOk(item) || isLogin(item) || isMfa(item) || item.path.includes('/Auth/Login'), 45000);
    if (info.path.includes('/Auth/Login')) {
      const provider = await clickDodoProvider(cdp);
      if (!provider.clicked) {
        return { ok: false, error: 'kb_provider_not_found', provider, final: publicInfo(await pageInfo(cdp)) };
      }
      info = await waitUntil(cdp, (item) => kbOk(item) || isLogin(item) || isMfa(item), 45000);
    }
    if (isLogin(info)) {
      const login = await submitCredentials(cdp, username, password);
      info = await waitUntil(cdp, (item) => kbOk(item) || isMfa(item) || isLogin(item), 50000);
      if (!login.changedUser || !login.changedPassword) {
        return { ok: false, error: 'login_form_not_filled', login, final: publicInfo(info) };
      }
    }
    if (isMfa(info)) {
      let latest;
      let resend_used = false;
      try {
        latest = await waitForNewDodoCode(baselineId, 35000);
      } catch {
        await clickSendEmailAgain(cdp);
        resend_used = true;
        latest = await waitForNewDodoCode(baselineId, 90000);
      }
      const submit = await submitMfa(cdp, latest.code);
      await sleep(5000);
      info = await waitUntil(
        cdp,
        (item) => kbOk(item) || isLogin(item) || isMfa(item) || /invalid|невер/i.test(item.text),
        60000,
      );
      if (!kbOk(info) && !/invalid|невер/i.test(info.text)) {
        await cdp.send('Page.navigate', { url: config.baseUrl + '/' });
        info = await waitUntil(cdp, (item) => kbOk(item) || isLogin(item) || isMfa(item), 45000);
      }
      if (!kbOk(info)) {
        return {
          ok: false,
          error: 'kb_auth_did_not_reach_knowledge_base',
          mail_message_id: latest.id,
          mail_code_source: latest.source,
          resend_used,
          submit,
          final: publicInfo(info),
          secrets_printed: false,
        };
      }
      const cookies = await getRelevantCookies(cdp);
      await writeJson600(config.sessionFile, {
        savedAt: new Date().toISOString(),
        baseUrl: config.baseUrl,
        finalUrl: `${info.host}${info.path}`,
        cookies,
        note: 'Knowledge Base session refreshed by dodo-bridge. Do not print or commit.',
      });
      return {
        ok: true,
        session_file: config.sessionFile,
        final: publicInfo(info),
        cookie_count: Object.keys(cookies).length,
        mail_message_id: latest.id,
        mail_code_source: latest.source,
        resend_used,
        secrets_printed: false,
      };
    }
    if (!kbOk(info)) {
      return { ok: false, error: 'kb_auth_unexpected_page', final: publicInfo(info) };
    }
    const cookies = await getRelevantCookies(cdp);
    await writeJson600(config.sessionFile, {
      savedAt: new Date().toISOString(),
      baseUrl: config.baseUrl,
      finalUrl: `${info.host}${info.path}`,
      cookies,
      note: 'Knowledge Base session refreshed by dodo-bridge. Do not print or commit.',
    });
    return {
      ok: true,
      session_file: config.sessionFile,
      final: publicInfo(info),
      cookie_count: Object.keys(cookies).length,
      mfa_required: false,
      secrets_printed: false,
    };
  });
}

async function main() {
  const action = process.argv[2] || process.env.DODO_KB_AUTH_BRIDGE_ACTION || 'status';
  let result;
  if (action === 'status') result = await status();
  else if (action === 'refresh') result = await refresh();
  else throw new Error(`Unknown action: ${action}`);
  console.log(JSON.stringify({ action, ...result }, null, 2));
  if (!result.ok) process.exitCode = 1;
}

main().catch((error) => {
  console.log(JSON.stringify({ ok: false, error: error.message.replace(/\b\d{6}\b/g, '******') }, null, 2));
  process.exit(1);
});
