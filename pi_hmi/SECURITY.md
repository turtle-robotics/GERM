# Publication review

The exported HMI application source, boot service, kiosk launcher, and dependency
inventory were checked for credentials before publication. Gitleaks 8.30.1 and
an additional pattern check found no embedded access credentials in the exported
application files. The repository's pre-existing Git history was also scanned.
These checks are evidence of review, not a guarantee against every possible
secret format.

The repository does not include SSH private/public keys, SSH connection notes,
passwords, host authentication files, virtual environments, historical backups,
the old ZIP archive, local databases, captured images, logs, or private audit
downloads. `.gitignore` excludes common credential and generated-data files.
The `germ` username and installation paths in the boot templates are deployment
examples, not authentication credentials.

The Flask application binds to all network interfaces and has no login system.
Use it on a trusted local network. Do not expose port 5000 directly to the public
Internet: control routes operate physical outputs, and firmware uploads replace
the Arduino program. The firmware-page token prevents a cross-site upload; it
does not authenticate people who can reach the HMI.

Keep machine-specific credentials outside the source tree. Review staged files
before every push; an ignore rule does not remove secrets already committed.
