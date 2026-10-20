# Release after the final milestone

The project owner requested a release **after the final milestone is complete**.
The dashboard branch is a development milestone, not a release. No tag or GitHub
release should be created as part of this branch.

## Finish the product

Complete the companion website using the Codewise-CLI reference, real product
screenshots and accurate installation/demo instructions. Finish deployment polish,
HTTPS/reverse-proxy guidance, credential setup, backup restoration and a recorded
walkthrough. Resolve blockers found by a fresh installation and review the final
scope before describing the project as ready for customer pilots.

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

Choose the release version after reviewing existing tags and compatibility changes.
Update the package version, lockfile, changelog and user-facing documentation together.
Write release notes explaining delivered behavior, setup/upgrade steps, known limits,
and validation. Include screenshot/demo links and the exact source commit.

After final validation and merge, create an annotated version tag and a GitHub release
from that exact `main` commit. Publish the corresponding version/commit-tagged container
image and record its digest. Do not relabel unrelated images or release an unreviewed
feature-branch snapshot. Verify the release links and installation artifact after
publication, then report the release URL and tag.

The user's release instruction applies at this final step; it is not a request to
publish an incomplete dashboard or website now.
