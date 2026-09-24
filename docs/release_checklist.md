# Release Checklist

Use this checklist before calling a revision reusable or attaching a version
tag.

## Code

- Run `pixi run test`.
- Confirm `git status --short` is empty.
- Confirm the final model commands in `configs/FINAL_MODELS.md` still match the
  fixed paper configurations.
- Run at least one no-submit operational dry run.

## Data

- Confirm `data/archive/operational/manifest.json` is tracked, or publish a
  versioned data pack.
- Run `pixi run operational-archive restore` in a clean clone.
- Run `pixi run check-data-pack --profile operational` and require
  `Missing: 0`.
- Record the archive coverage dates and SHA256 checksum in the release notes.
- Do not include raw GRIB files, API keys, `.env`, logs, or machine-specific
  mount paths.

## Documentation

- Follow `docs/user_guide.md` from a clean clone.
- Verify all documented Pixi task names against `pixi.toml`.
- Explain the difference between retrospective paper configs and live cutoff
  adapters.
- Update `CITATION.cff` with the final paper citation when available.

## Distribution

- Select and add a `LICENSE` file.
- Tag the code and data with matching versions.
- Publish large immutable data packs as release assets, on Zenodo/OSF, or in an
  institutional repository rather than committing tar archives to Git.
- Keep the Synergie copy as disaster recovery, not as the only user-accessible
  data source.
