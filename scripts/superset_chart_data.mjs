#!/usr/bin/env node
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const DEFAULT_DOMAINS = [
  'analytics.dodois.io',
  'officemanager.dodois.io',
  'auth.dodois.io',
  'admin.dodois.io',
  '.dodois.io',
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function stdinJson() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
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
    await sleep(300);
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

async function loadSessionCookies(sessionFiles) {
  const cookies = [];
  for (const sessionFile of sessionFiles) {
    if (!sessionFile) continue;
    try {
      const session = JSON.parse(await fs.readFile(sessionFile, 'utf8'));
      const source = session.cookies || session;
      if (Array.isArray(source)) {
        for (const item of source) {
          if (item?.name && item?.value) cookies.push({ name: item.name, value: item.value });
        }
      } else {
        for (const [name, value] of Object.entries(source || {})) {
          if (typeof value === 'string' && value) cookies.push({ name, value });
        }
      }
    } catch {
      // Missing or stale session files are allowed; final Superset request will fail if none work.
    }
  }
  return cookies;
}

async function main() {
  const request = await stdinJson();
  const chrome = process.env.SUPERSET_CHROME_PATH
    || process.env.DODO_AUTH_CHROME_PATH
    || '/usr/bin/google-chrome';
  const dashboardUrl = process.env.SUPERSET_DASHBOARD_URL
    || `${request.base_url || 'https://analytics.dodois.io'}/superset/welcome/`;
  const sessionFiles = (process.env.SUPERSET_SESSION_FILES || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  const domains = (process.env.SUPERSET_COOKIE_DOMAINS || DEFAULT_DOMAINS.join(','))
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

  const port = 20400 + Math.floor(Math.random() * 400);
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'dodo-bridge-superset-'));
  const child = spawn(chrome, [
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    'about:blank',
  ], { stdio: 'ignore' });

  try {
    await waitJson(`http://127.0.0.1:${port}/json/version`);
    const targets = await waitJson(`http://127.0.0.1:${port}/json/list`);
    const pageTarget = targets.find((target) => target.type === 'page');
    if (!pageTarget) throw new Error('No CDP page target found');
    const cdp = await connectCdp(pageTarget.webSocketDebuggerUrl);
    try {
      await cdp.send('Network.enable');
      await cdp.send('Page.enable');
      await cdp.send('Runtime.enable');

      const cookies = await loadSessionCookies(sessionFiles);
      for (const cookie of cookies) {
        for (const domain of domains) {
          await cdp.send('Network.setCookie', {
            name: cookie.name,
            value: cookie.value,
            domain,
            path: '/',
            secure: true,
            httpOnly: !cookie.name.startsWith('SelectedLanguage'),
            sameSite: 'None',
          }).catch(() => null);
        }
      }

      await cdp.send('Page.navigate', { url: dashboardUrl });
      await sleep(Number(process.env.SUPERSET_DASHBOARD_WAIT_MS || 5000));

      const expression = `
        (async () => {
          const response = { ok: false };
          try {
            const csrfResp = await fetch('/api/v1/security/csrf_token/', {
              credentials: 'include',
              headers: { Accept: 'application/json' },
            });
            const csrfText = await csrfResp.text();
            if (!csrfResp.ok) {
              return { ok: false, stage: 'csrf', status: csrfResp.status, text: csrfText.slice(0, 500), href: location.href };
            }
            const csrf = JSON.parse(csrfText).result;
            const dataResp = await fetch(${JSON.stringify(new URL(request.url).pathname + new URL(request.url).search)}, {
              method: ${JSON.stringify(request.method || 'POST')},
              credentials: 'include',
              headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf,
                'X-Requested-With': 'XMLHttpRequest',
              },
              body: JSON.stringify(${JSON.stringify(request.json)}),
            });
            const text = await dataResp.text();
            return {
              ok: dataResp.ok,
              stage: 'chart_data',
              status: dataResp.status,
              text,
              href: location.href,
            };
          } catch (error) {
            response.stage = 'exception';
            response.error = String(error?.stack || error);
            response.href = location.href;
            return response;
          }
        })()
      `;
      const evaluated = await cdp.send('Runtime.evaluate', {
        expression,
        awaitPromise: true,
        returnByValue: true,
      });
      const value = evaluated.result.value;
      if (!value?.ok) {
        throw new Error(`Superset browser fetch failed at ${value?.stage}: ${value?.status || ''} ${(value?.text || value?.error || '').slice(0, 500)}`);
      }
      process.stdout.write(value.text);
    } finally {
      cdp.close();
    }
  } finally {
    child.kill('SIGTERM');
    await fs.rm(profile, { recursive: true, force: true }).catch(() => null);
  }
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exit(1);
});
