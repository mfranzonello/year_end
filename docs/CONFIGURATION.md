# Runtime configuration and device sync

`config/api.toml`, `config/drives.toml`, and `config/webhooks.toml` are ignored
installation configuration. Their tracked `.example.toml` counterparts are
reference templates only. Copy and complete every `REPLACE_ME` value with the
appropriate TOML type (for example, an integer without quotes for a numeric
setting). The loader rejects incomplete templates and never reads examples.
Standard provider endpoints and API scope identifiers may remain in examples.

For each document, the corresponding environment variable takes precedence over
the **entire** local file, without merging:

| Local file | Environment variable containing TOML text |
| --- | --- |
| `config/api.toml` | `YEAR_END_CONFIG_API_TOML` |
| `config/drives.toml` | `YEAR_END_CONFIG_DRIVES_TOML` |
| `config/webhooks.toml` | `YEAR_END_CONFIG_WEBHOOKS_TOML` |

Missing configuration, empty environment variables, malformed TOML, and
unreplaced placeholders fail explicitly. Values are not included in parser errors.
Secrets remain in the existing local/Azure secret stores; never put credentials
in these documents or GitHub variables. GitHub variables are readable by people
with the appropriate repository access and are not automatically log-masked.

## GitHub Actions and Azure Functions

The workflows explicitly map GitHub `vars` to these environment variables. The
existing GitHub environment is named `production`; this is independent of the
Git branches `qa`, `dev`, and `main`. Configure the selected scope before promoting
these workflow changes. Missing variables intentionally stop the workflow.

Cloud migration and inspection require API and drives configuration. Subscription
renewal and Function deployment require API and webhook configuration. The Function
deployment validates and writes its selected runtime config into the private
deployment package: GitHub runner environment variables do not automatically
persist on Azure. No example files are copied into runtime configuration.

## Preview and synchronize

Install GitHub CLI and authenticate with `gh auth login`. The account needs
Variables read/write access for the selected repository/environment. The script
uses GitHub CLI's authenticated API operations, passing document values through
stdin rather than command arguments. It never prints the documents or API errors.
It synchronizes one explicit non-secret document at a time and preserves comments.

```powershell
# Preview an upload to the existing Actions environment.
.\.venv\Scripts\python.exe -m integrations.github.config_sync push api --repo OWNER/REPO --environment production
# Apply after reviewing the local document and preview.
.\.venv\Scripts\python.exe -m integrations.github.config_sync push api --repo OWNER/REPO --environment production --apply
# Preview a download on another device.
.\.venv\Scripts\python.exe -m integrations.github.config_sync pull api --repo OWNER/REPO --environment production
# Write a missing local file. Add --overwrite only to replace an existing file.
.\.venv\Scripts\python.exe -m integrations.github.config_sync pull api --repo OWNER/REPO --environment production --apply
```

Use `drives` or `webhooks` in place of `api`. Omit `--environment` to use repository
variables. `--file` selects an alternate input/output TOML file; examples are
rejected. Synchronization is manual, with no background upload or automatic merge.
GitHub's last uploaded document is the shared copy; preview before replacing it.
Device-specific executable and mount settings may differ: download with `--file`
to an ignored location and compare locally before replacing another device's config.

Removing these files from tracking does not remove past values from Git history.
