# Publish version 2.0.1 after final review

Version 2.0.1 is a focused security and release-consistency patch. It updates affected
Starlette and OpenTelemetry API dependency lines, audits locked runtime dependencies in
CI, and adds regression coverage for Host, origin and static security-header handling.
It also gives the post-2.0.0 changes on `main` a distinct application version.

## Validate the release candidate

Use the reviewed `main` commit after the security patch is merged. Recheck:

- Locked installation and runtime dependency audit.
- Backend tests, linting and formatting.
- Browser sign-in, service management, outage/recovery, alert delivery and mobile layout.
- Runtime image construction, non-root/read-only startup and restart persistence.
- Base, demonstration and production Compose configuration.
- Database backup/restore and upgrade behavior.

Read the outcomes: skipped, failed or unrun checks cannot be described as passed. Keep
credentials out of source, require secure production cookies and TLS, and keep
operational interfaces internal.

## Publish the patch release

Package metadata, runtime metadata, changelog, lockfile and
`docs/releases/v2.0.1.md` must agree before tagging. Do not modify or recreate the
existing `v2.0.0` tag.

After final validation and merge, create the annotated tag from the exact reviewed
`main` commit and push it only with the project owner's approval:

```bash
git switch main
git pull --ff-only
git tag -a v2.0.1 -m "System Monitoring 2.0.1"
git push origin v2.0.1
```

The tag workflow repeats backend and container validation, publishes semver and commit
tags to GitHub Container Registry, records the immutable digest, and creates the GitHub
release from the reviewed notes. Verify the workflow, container digest and release URL
after publication. If a release check fails, fix it on a reviewed branch and use a new
patch version rather than replacing a public tag.
