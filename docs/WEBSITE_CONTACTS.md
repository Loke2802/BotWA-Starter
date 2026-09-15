# Website contact registration — staging rollout

`POST /website/public/contacts` is a write-only public registration endpoint.
It uses the existing contact table, tenant-scoped HMAC identity and Fernet cipher.
No schema migration is required. Existing contact administration and portal
permissions remain unchanged.

The feature is disabled by default. Configure only on the staging API:

```text
LURI_PUBLIC_CONTACTS_ENABLED=true
LURI_PUBLIC_CONTACTS_ORGANIZATION_ID=<existing test organization UUID>
LURI_PUBLIC_CONTACTS_ORIGINS=http://localhost:3002
```

Use the existing `CONTACT_IDENTITY_HMAC_KEY` and WhatsApp encryption configuration.
Do not rotate those keys for this feature. Add an exact preview HTTPS origin only
when needed; do not connect the live commercial website to staging.

The browser build needs:

```text
NEXT_PUBLIC_LURI_CONTACTS_URL=https://staging-api.kalivur.com/website/public/contacts
NEXT_PUBLIC_LURI_CONTACTS_ENVIRONMENT=staging
```

Request example (synthetic data only):

```json
{"name":"Cliente de prueba","whatsapp":"+51900000001","consent":true,"notice_version":"contact-registration-v1"}
```

Success is `200 {"accepted":true}` for both new and existing identities. The
endpoint never exposes IDs, existing names, or whether a contact existed.
New records include encrypted source, consent purpose/version/time, and an
unverified identity marker in notes. A submitted phone number is not proof of
ownership. The endpoint does not send WhatsApp messages or subscribe marketing.
For existing identities it does not overwrite names/notes or reactivate archived
contacts. It registers initial contact details, not inquiry history.

## Verification before enabling

1. Deploy the reviewed image to staging; preserve all existing app configuration.
2. Obtain the test organization's UUID from the authenticated portal/API.
3. Configure the three backend variables above and restart the API.
4. Check preflight allows the exact preview origin; unknown origins are denied.
5. Submit a synthetic contact from the local website and check it appears in the
   authenticated contacts API/portal for that organization.
6. Repeat the submission; confirm one contact, and unchanged existing details.
7. Confirm a user from a different organization cannot read it.
8. Archive the synthetic contact after verification. Do not delete real records.

The process-local rate limit (12/min per connection peer, 120/min total) is a
bounded staging safeguard. Before production or multiple replicas, add shared
ingress abuse protection. Do not trust client-supplied forwarding headers.
The allowlisted Origin is not authentication. Authenticated CRM endpoints retain
their own permission checks; this endpoint only accepts registrations.

Rollback: set `LURI_PUBLIC_CONTACTS_ENABLED=false` and redeploy/restart. Existing
contacts remain intact. Hide the web form by clearing its endpoint and rebuilding.
