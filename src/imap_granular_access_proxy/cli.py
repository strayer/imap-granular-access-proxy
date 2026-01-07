"""Command-line interface for the IMAP Granular Access Proxy."""

import argparse
import sys


def main() -> int:
    """Entry point for the IMAP proxy CLI."""
    parser = argparse.ArgumentParser(
        prog="imap-proxy",
        description="IMAP Granular Access Proxy - Secure, per-folder IMAP access control",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=9993,
        help="Port to listen on (default: 9993)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    args = parser.parse_args()

    # TODO: Implement proxy startup logic
    print(f"IMAP Granular Access Proxy starting on {args.host}:{args.port}")
    print(f"Using config: {args.config}")
    print("Not yet implemented.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
