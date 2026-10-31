# Dependency security follow-up before the staging pilot

The dependency audit rerun against master 026ca10 reported 15 advisories in
certifi 2026.7.22 and PyJWT 2.13.0. Fourteen have published patched versions;
PYSEC-2026-4146 / GHSA-gvp8-978c-rx2q has no published fix in the audit feed.
A historical passing CI result does not cover advisories disclosed afterward.

## Change

- Require PyJWT >=2.15.1 and lock 2.15.1 in runtime and development requirements.
  This includes the 2.14/2.15 security fixes and the 2.15.1 padding compatibility fix.
- Require certifi >=2026.10.19 explicitly so dependency resolution cannot select
  the earlier CA bundle. Lock the patched bundle in both requirements files.
- Update only these two hashed lock blocks; preserve Linux-only dependencies
  and all unrelated locked versions. The repository lock validator checks the
  resulting files against pip-compile.
- No application behavior, migrations, tenancy, flags, infrastructure, secrets,
  or model calls change. A new validated image is still required to update staging.

## Remaining advisory

GHSA-gvp8-978c-rx2q concerns reusing and mutating an options dictionary across
unverified and verified JWT decoding calls. Luri's AccessTokenService uses the
single allowed HS256 algorithm, verifies signatures, and supplies no options
argument. The described shared-options path is not used there. The dependency
advisory remains tracked and is not suppressed in the audit tool; the repository
policy reports findings without a published fix and fails on actionable ones.
This review is not a claim that every dependency advisory is exploitable in Luri.

## Validation

Run the canonical quality, lock, dependency, PostgreSQL and container jobs on
this PR before rollout. Local validation uses isolated copies of just the updated
packages and never calls a paid model. Full PostgreSQL, adjacent migration cycle,
image scanning and source secret scanning remain CI requirements.

## Rollout and rollback

After review and all required checks, build/publish the immutable master image
through the existing CI workflow and update only the existing staging API,
worker and migration job to its digest and matching build SHA. Keep AI disabled,
empty pilot scopes and WhatsApp live disabled. Verify health, version, database
revision and protected metrics again. No production rollout is authorized by
this dependency change. No migration or schema downgrade is required to revert
the application image; reverting these dependency fixes restores known findings.

## Primary sources

- [certifi advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2)
- [PyJWT changelog](https://pyjwt.readthedocs.io/en/stable/changelog.html)
- [PyJWT OKP advisory](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-x33g-cr3x-6449)
- [Unfixed shared-options advisory](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-gvp8-978c-rx2q)
