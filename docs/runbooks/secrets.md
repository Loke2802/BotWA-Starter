# Secret operations runbook

## Categories

- database runtime and migration credentials;
- JWT authentication signing secret;
- identity/rate-limit HMAC keys and audit cursor keyset;
- WhatsApp and integration encryption current/previous keys;
- OAuth state key, Google OAuth credentials, and callback configuration;
- Meta/WhatsApp and Mercado Pago credentials/webhook secrets;
- observability metrics bearer token;
- safe deployment metadata (`BOTWA_BUILD_SHA` is identity, not a secret).

Provision separate values per environment through runtime secret injection.
Never commit, bake into an image, upload as a workflow artifact, print, or copy a
`.env` file into staging/production. CI pull requests receive no deployment
secrets. The only trusted publication credential is the scoped GitHub token in
the `master` GHCR job.

Rotation impact differs by class. Preserve explicitly supported previous Fernet
keys until encrypted records are rewrapped. Coordinate JWT rotation with active
sessions. Rotate identity HMAC keys only with an identity migration plan. Keep
audit cursor keysets compatible with accepted cursors. Rotate OAuth-state and
metrics keys with short overlap and endpoint verification. Provider credentials
require provider-side revocation and real smoke validation.

Back up critical encryption keys in an approved external recovery system. Test
authorized recovery without displaying values. Loss of those keys can make
persisted encrypted content permanently unreadable.
