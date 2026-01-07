# Project Goals: imap-granular-access-proxy

## 1. Project Overview

**imap-granular-access-proxy** is a lightweight, open-source middleware application acting as a Man-in-the-Middle (MITM) between an email client and an upstream IMAP server (e.g., Gmail, Outlook, Dovecot).

The primary purpose is to allow third-party applications to access an inbox with **restricted, granular permissions**, protecting the main account credentials and preventing unauthorized actions (like wiping the inbox) while allowing necessary workflows (like moving processed emails).

**License:** GNU Affero General Public License v3.0 (AGPL-3.0).

## 2. Core Philosophy

- **Simple & Robust:** Built on **Python** and **Twisted**.
- **Security First:** The upstream password never leaves this application. Clients only possess limited-scope tokens.
- **Verify, Don't Trust:** The application assumes the client is buggy or malicious. Every command is checked against an ACL before forwarding.
- **Test-Driven Security:** Security features must be verified by automated tests. If it isn't tested, it doesn't exist.

## 3. Functional Requirements (Epics)

### Epic A: The Proxy Engine

- Implement a TCP server listening on a local port (e.g., `9993`).
- Implement an Upstream IMAP Client connection logic that handles multiple distinct upstream servers.
- Correctly handle TLS/SSL encryption for both incoming and outgoing connections.

### Epic B: Configuration & Auth Architecture

- **Upstream Registry:** Define real IMAP accounts (Host/User/Pass) _once_ in the config.
- **Local User Registry:** Define multiple local "virtual users."
- **Mapping:** Each local user is mapped to exactly one Upstream account, but multiple local users can map to the _same_ Upstream account (with different permissions).

### Epic C: Folder Scoping & Virtual Views

- **Directory Filtering:** Intercept `LIST` and `LSUB`.
- **Regex Matching:** Allow folders to be defined by explicit names or Regex patterns (e.g., `Invoices/*`).
- **Hidden by Default:** If a folder is not explicitly matched in the user's config, it does not exist for that user. Attempts to `SELECT` it result in `NO [ALERT] Access Denied`.

### Epic D: Granular Command Filtering

- **Per-Folder Permissions:** Permissions are no longer global; they are applied to specific folders.
- **Action Categories:**
  - `view`: Can see the folder in lists and `SELECT` it.
  - `read`: Can `FETCH` body/headers.
  - `write_flags`: Can change flags (e.g., Mark as Read/Starred).
  - `delete_msgs`: Can mark as `\Deleted` and `EXPUNGE`.
  - `append`: Can `APPEND` (upload) emails or `COPY/MOVE` emails _into_ this folder.
- **Logic:**
  - To **Move** an email from A to B, the user needs `read` + `delete_msgs` on A, and `append` on B.

## 4. Configuration Specification

Configuration will be in YAML. It separates "Remotes" (Real accounts) from "Clients" (Restricted Access).

**Conceptual Schema:**

```yaml
# 1. Define the real servers
upstreams:
  personal_gmail:
    host: "imap.gmail.com"
    port: 993
    username: "me@gmail.com"
    password: "env:GMAIL_PASSWORD" # Support ENV or literal string

  work_outlook:
    host: "outlook.office365.com"
    port: 993
    username: "me@work.com"
    password: "real_work_password"

# 2. Define the limited access users
users:
  # Case: A scraper that reads invoices and moves them to "Processed"
  - username: "invoice_bot"
    password: "token_123"
    upstream: "personal_gmail" # References key in 'upstreams'
    rules:
      - folders: ["Invoices"]
        access: ["view", "read", "write_flags", "delete_msgs"] # Can read and remove

      - folders: ["Invoices/Processed"]
        access: ["view", "append"] # Can only put things here, not read/delete

      # Implicit Deny: Cannot see "Inbox", "Sent", etc.

  # Case: A backup tool that can read everything but delete nothing
  - username: "backup_daemon"
    password: "token_456"
    upstream: "work_outlook"
    rules:
      - folders: [".*"] # Regex for all folders
        access: ["view", "read"] # Strictly Read-Only
```

## 5. Quality Assurance & Testing Goals

Since this is a security application, "it works on my machine" is insufficient.

- **100% Test Coverage:** Mandatory for `protocol.py` (or equivalent), the ACL logic, and the configuration parser.
- **Negative Testing:** Tests must explicitly prove that:
  - A user _cannot_ select a folder they aren't allowed to see.
  - A user _cannot_ delete an email if they only have `read` permission.
  - A user _cannot_ send SMTP commands (though this is enforced by not listening on SMTP ports).
- **Integration Tests:** A test suite that spins up a mock IMAP server (or uses a Dockerized Dovecot), runs the Proxy, and uses a standard Python client (`imaplib`) to verify permission enforcement end-to-end.

## 6. Non-Goals

- **No SMTP:** This application will **not** listen on SMTP ports.
- **No Storage:** No emails are stored on disk.
- **No GUI:** CLI and Config file only.

## 7. Technical Stack

- **Language:** Python 3.x
- **Framework:** Twisted (`twisted.mail.imap4`).
- **Testing:** `pytest` and `twisted.trial`.

