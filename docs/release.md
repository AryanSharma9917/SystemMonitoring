# Publish version 2.0.0 after final review

The final feature milestone prepares version 2.0.0, but the release must point at the
reviewed `main` commit. Do not tag the feature branch. Merge it first, confirm the
resulting commit and repeat the release-candidate checks from that exact source.

## Finish the product

The companion website, real screenshots, recorded browser walkthrough, HTTPS overlay,
backup/restore tooling and operational runbooks are now included. The supported pilot
scope remains one administrator and one application process per isolated customer.

## Validate the release candidate

Use the reviewed `main` commit after the final feature branch is merged. Recheck:

- Locked installation, backend checks, formatting and the runtime image.
- Browser sign-in, service creation/editing, checks, incidents, retries, charts,
  responsive layout, session expiry and logout.
- Real scheduled outage/recovery, delivery to a controlled webhook receiver and
  the operational dashboard queries.
- Upgrade from the previous schema, a backup restore and documented rollback.
- Website links, actual screenshots and the complete deployment instructions.

Read the outcomes: skipped, failed or unrun checks cannot be described as passed.
Keep default passwords out of the project, require secure production cookies/TLS,
and ensure operational interfaces remain internal.

## Publish the project release

The repository already has the historical `v1.0` release from August 15, 2024. This
modernization changes authentication, deployment and the application contract, so the
selected release is `v2.0.0`. Package metadata, lockfile, changelog and
`docs/releases/v2.0.0.md` must agree before tagging. The release notes explain setup,
upgrade, rollback and known limits.

After final validation and merge, create an annotated version tag from the exact main
commit and push it:

```bash
git switch main
git pull --ff-only
git tag -a v2.0.0 -m "System Monitoring 2.0.0"
git push origin v2.0.0
```

The tag workflow repeats backend and container validation, publishes semver and commit
tags to GitHub Container Registry, records the immutable digest, and creates the GitHub
release. Verify the workflow, release URL, Pages URL, container digest and installation
artifact after publication. Never move or recreate the release tag after publication.

If any release check fails, fix it on a reviewed branch and tag a new patch version;
do not replace an existing public tag.
