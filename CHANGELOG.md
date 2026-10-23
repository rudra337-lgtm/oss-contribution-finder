# Changelog

## [Unreleased]

### Added
- Initial release
- `opportunity_score()` ranks an issue by acceptance probability (#28): low
  competition tiers by stars (<=500 -> 1.0, <=5000 -> 0.5, else 0.1), label
  tiers (`good first issue` > `help wanted` > `bug`) and unassigned issues, so
  a 200-star good-first-issue repo outranks a 50k-star one.
- `--sort score` ranks results locally with `opportunity_score` (the search
  itself is sent as `sort=updated`; the GitHub API would reject the
  client-side key).

### Changed
- Extracted `build_parser()` from `main()` so the CLI surface can be unit-tested
  without patching `sys.argv`. No behaviour change: `--help` output is
  byte-identical.
