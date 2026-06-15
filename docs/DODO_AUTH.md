# Dodo IS Web Authorization

This bridge includes an internal web flow for refreshing Dodo IS
OfficeManager/admin sessions and submitting the email MFA code.

## Routes

- `GET /auth/dodo` - web form.
- `POST /auth/dodo/status` - check saved session health.
- `POST /auth/dodo/refresh` - start or refresh authorization.
- `POST /auth/dodo/submit-code` - submit a 6-digit email MFA code to the saved
  pending context.

## Helper Command

Configure:

```env
DODO_AUTH_HELPER_COMMAND=node scripts/dodo_auth_flow.mjs
DODO_AUTH_CHROME_PATH=/home/ubuntu/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome
DODO_AUTH_SECRET_DIR=/home/ubuntu/.openclaw/secret
```

The helper intentionally follows the OpenClaw pattern:

1. Start headless Chromium with CDP enabled.
2. Load saved Dodo cookies from `DODO_AUTH_SECRET_DIR`.
3. Check OfficeManager and admin pages.
4. If login is needed, use the local credential file.
5. If MFA is required, save a pending context.
6. When a fresh code is submitted, reopen the pending context, submit the code,
   and save updated session files.

## Security Notes

- Do not expose `/auth/dodo` publicly without HTTPS and bridge API-key
  protection.
- The MFA code is passed to the helper through stdin, not command-line
  arguments.
- Helper output is redacted by the bridge before it is returned.
- This is an admin workflow, not a normal ChatGPT tool. It should remain outside
  the LLM tool registry.

