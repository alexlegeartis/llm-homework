"""Two-step Colab CLI authentication.

``colab``'s built-in flow prints a URL and then blocks on ``input()`` waiting for the
authorization code. That needs one long-lived interactive process: if it is killed
between the token exchange and the write of ``token.json`` -- which is what happened
here, the exchange succeeded but nothing was persisted -- the credentials are lost and
the flow must be repeated.

This splits the flow across two invocations so nothing has to stay alive in between:

    --start           print the authorization URL, persist the PKCE verifier
    --finish CODE     exchange the code, write ~/.config/colab-cli/token.json

The output is exactly the file ``colab_cli.auth`` would have written (same client
config, same scopes, same redirect), so the CLI picks it up with no further changes.

Run it with the CLI's dependencies available, e.g.

    uv run --python 3.12 --with google-auth-oauthlib colab_auth.py --start
"""

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# Mirrors colab_cli/auth.py -- keep in sync if the CLI changes.
PUBLIC_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/colaboratory",
    "https://www.googleapis.com/auth/drive.file",
]
REMOTE_REDIRECT_URI = "https://sdk.cloud.google.com/applicationdefaultauthcode.html"
TOKEN_CONFIG_PATH = Path(os.path.expanduser("~/.config/colab-cli/token.json"))

# The pending PKCE verifier: secret but short-lived, so it stays out of the repo.
PENDING_PATH = Path(os.path.expanduser("~/.config/colab-cli/.pending_auth.json"))

CLIENT_CONFIG_PATH = Path(
    os.path.expanduser(
        "~/AppData/Roaming/uv/tools/google-colab-cli/Lib/site-packages/colab_cli/oauth_config.json"
    )
)


def _client_config():
    if not CLIENT_CONFIG_PATH.is_file():
        sys.exit(f"client config not found at {CLIENT_CONFIG_PATH}")
    return json.loads(CLIENT_CONFIG_PATH.read_text())


def start():
    flow = InstalledAppFlow.from_client_config(_client_config(), PUBLIC_SCOPES)
    flow.redirect_uri = REMOTE_REDIRECT_URI

    # Pin the verifier instead of letting the library autogenerate one, so it can be
    # persisted and reused by --finish.
    flow.code_verifier = secrets.token_urlsafe(64)
    auth_url, state = flow.authorization_url(prompt="consent", token_usage="remote")

    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps({"code_verifier": flow.code_verifier, "state": state}))

    print("\nOpen this URL, approve access, and copy the authorization code:\n")
    print(auth_url)
    print(f"\n(PKCE verifier saved to {PENDING_PATH})")
    return 0


def finish(code):
    if not PENDING_PATH.is_file():
        sys.exit("no pending authorization; run --start first")
    pending = json.loads(PENDING_PATH.read_text())

    flow = InstalledAppFlow.from_client_config(
        _client_config(), PUBLIC_SCOPES, state=pending["state"]
    )
    flow.redirect_uri = REMOTE_REDIRECT_URI
    flow.code_verifier = pending["code_verifier"]

    flow.fetch_token(code=code.strip())

    TOKEN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CONFIG_PATH.write_text(flow.credentials.to_json())
    PENDING_PATH.unlink(missing_ok=True)

    print(f"wrote {TOKEN_CONFIG_PATH}")
    print("has refresh_token:", bool(flow.credentials.refresh_token))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--start", action="store_true", help="print the authorization URL")
    group.add_argument("--finish", metavar="CODE", help="exchange the authorization code")
    args = parser.parse_args()

    raise SystemExit(start() if args.start else finish(args.finish))
