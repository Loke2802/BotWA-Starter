# Infrastructure go-live checklist

PRD-023 does not claim staging or production deployment. Before either is
enabled, owners must record decisions and evidence for every applicable item.

- [ ] Hosting/container runtime approved; capacity and restart policy defined.
- [ ] GHCR visibility and pull authorization approved.
- [ ] Immutable master SHA/digest selected; active and previous digest retained.
- [ ] DNS and HTTPS/TLS termination configured.
- [ ] Trusted proxy addresses, allowed hosts, and CORS origins explicitly set.
- [ ] Stable HTTPS Meta and Mercado Pago webhook routes verified.
- [ ] Secret manager selected; staging/production values fully isolated.
- [ ] Encryption-key backup/recovery and class-specific rotation tested.
- [ ] PostgreSQL provider, TLS/CA, runtime role, and migration role approved.
- [ ] Backup/snapshot gate and periodic restore test evidenced.
- [ ] RPO/RTO approved by business/operations.
- [ ] GitHub `master` ruleset requires PR plus `quality`, `tests`, `postgresql`,
      and `container-security`; force push/deletion policy approved.
- [ ] Secret Scanning, Push Protection, and Dependabot security updates enabled.
- [ ] `staging` and `production` GitHub Environments/reviewers configured.
- [ ] Internal metrics scrape, bearer token, network restriction, JSON log
      collection, retention, dashboards, and alert destination configured.
- [ ] Alerts cover DB readiness, 5xx, latency, provider failures/timeouts,
      Billing failure, Automation stall/failure, and rate-limit persistence.
- [ ] Platform scheduler runs Billing Due Transitions without overlap.
- [ ] Meta live credential and webhook/send smoke passed.
- [ ] Google OAuth consent/callback/refresh/Calendar List/FreeBusy smoke passed.
- [ ] Mercado Pago sandbox and commercial configuration smoke passed.
- [ ] Deployment and rollback drills completed with recorded SHA/digest/revision.
