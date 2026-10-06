# Repository-linked container releases

Target confirmed by the owner on 6 October 2026: existing Unraid server and GitHub Container Registry. Source: `https://github.com/maroge1990/Pig-Music`. Image: `ghcr.io/maroge1990/pig-music`.

The container workflow builds the pinned Dockerfile, tests that exact image with the backend suite, and runs both artwork benchmarks under a 1 GB memory limit before publication. Frontend build happens inside Docker; frontend tests and formatting run separately. Pull requests only validate. Branch pushes publish a source-commit candidate; version tags also publish the version name. No workflow deploys to Unraid and no mutable `latest` tag is used.

Each published image records its source repository, full commit and version as OCI labels. The Actions summary supplies the immutable `ghcr.io/maroge1990/pig-music@sha256:...` reference. The source label connects the package to the GitHub repository. Package visibility must remain private; publication does not authorise making the repository or package public.

## Unraid preparation

For a private package, configure registry pull access on Unraid using a GitHub credential with `read:packages`. Use `docker login ghcr.io --username maroge1990 --password-stdin`, supplying the token through a protected input. Never put the credential into Compose, Git, documentation, commands recorded in shell history, or build arguments. No credentials are bundled into the image.

Keep the existing NAS mount, appdata directory, private networking/static address, embedded engine, 1 GB limit and UID/GID protections. `compose.unraid-registry.yaml` is an optional overlay on the current household Compose; it changes only the image and source label. Existing container/appdata names are retained to avoid an incidental storage or topology migration.

Do not run Compose over the live deployment directly. The established deployment tool creates a unique project, preserves the old container and performs stopped-state backup and migration checks.

## Verify a published candidate

Check out the exact commit shown by the image's revision label, with a clean tracked tree. Replace the examples with an unused release name, actual digest and an authorised SSH key:

```sh
python scripts/deploy_unraid.py \
  --version registry-yyyymmdd-v1 \
  --image ghcr.io/maroge1990/pig-music@sha256:<full-digest> \
  --key /path/to/unraid-key
```

The tool pulls the immutable image, verifies its source and commit labels against the local checkout, runs isolated image tests and the scale gate, and leaves the existing service running. It never rebuilds or silently substitutes a registry image.

For a separately authorised live release, use a new release suffix and add `--deploy` in that invocation. The existing active-transfer checks, original settings, stopped-state backup, disposable migration verification, rollback container, unique Compose project and private addressing remain in force. The normal source-build mode remains available for recovery.

Rollback uses the retained container/image plus its matching state backup as documented in operations. Do not delete old images, backup directories or retired-manager recovery material during this transition.

## Current access and evidence

GitHub access, Actions publication, Unraid registry pull access and dedicated SSH access are verified. The owner provisioned the deployment public key; private keys and registry credentials remain outside the repository.

On 7 October 2026 the authorised release `registry-20261007-v1` deployed:

- Image: `ghcr.io/maroge1990/pig-music@sha256:e2db668bfb99e41102cfbe6a8f6ad7b975262326347467057c1d39029b4dba8b`.
- Revision: `e3fc247a5bd183d0787281319a7076da3f2cd781`; source label matches this repository. [Publishing run](https://github.com/maroge1990/Pig-Music/actions/runs/37445421140) passed.
- Exact-image verification: 117 backend tests plus 10k/50k artwork benchmarks under 1 GB, repeated on Unraid. Stopped-state migration retained all 1,395 tracks, links and durable rows.
- Live read-only checks: healthy service, available NAS, 1,395 readable files, 25 matching managed hashes, 98 albums, 27 completed queue rows and original download settings. Artwork files/responses verified.
- Existing private address, NAS/appdata mounts, UID/GID 99:100, read-only root and 1 GB limit retained.
- Rollback: stopped container `pig-music-preview-before-registry-20261007-v1` and matching state backup `/mnt/user/appdata/pig-music-preview/backups/pre-registry-20261007-v1`.
- Release input: `/mnt/user/appdata/pig-music-preview/releases/registry-20261007-v1`. Later native/documentation commits do not change the running digest. Draft PRs remain unmerged.
