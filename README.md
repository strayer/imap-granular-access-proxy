# IMAP Granular Access Proxy

A lightweight, open-source IMAP proxy that provides granular, per-folder access control for third-party applications.

## Overview

This proxy acts as a middleware between email clients and upstream IMAP servers (Gmail, Outlook, Dovecot, etc.), allowing you to grant restricted permissions to applications without exposing your full account credentials.

## Features

- **Per-folder permissions**: Grant read, write, delete, or append access on a folder-by-folder basis
- **Multiple virtual users**: Create multiple restricted access profiles for a single upstream account
- **Regex folder matching**: Define access rules using patterns like `Invoices/*`
- **Secure by design**: Upstream credentials never leave the proxy; clients only receive limited-scope tokens

## Installation

```bash
uv sync
```

## Usage

```bash
uv run imap-proxy --config config.yaml --port 9993
```

## Configuration

See `GOALS.md` for the configuration specification.

## License

AGPL-3.0-only
