# Public-copy boundaries

This directory was assembled from an explicit source-file allowlist, not a copy of the working application folder or its Git history.

Included: application source, synthetic tests and fixtures, generated icon artwork, generic development configuration, and new public documentation.

Excluded: account tokens, OAuth records, SSH keys, Excel feed keys, personal profiles, real listings, proposals, bids, review history, databases, workbooks, logs, backups, installed application bundles, caches, and Git history.

Personal host/user defaults and the app identifier were replaced with generic demo values. Runtime credential paths use a separate demo namespace. The default entry point uses fictional fixtures and its own local state folder; it does not connect to the private installation.

The demo's review interface allows only local snapshot, review, sample reload, activity and export actions. Source integrations and bid workflows remain as unconfigured reference code, tested with mocks. Do not run live integration entry points unless you deliberately configure them with your own credentials and review their behavior.

The release package is checked for known credential matches, personal identifiers, private-key formats, unexpected files and runtime artifacts. These checks complement manual review; they are not a guarantee about future edits. Keep credentials outside the repository, and review the staged diff before every publication. `.gitignore` is a convenience, not a security boundary.
