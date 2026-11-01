"""Stop the Colab CLI from writing OAuth secrets to disk in plaintext.

``colab_cli/common.py::setup_logging`` unconditionally does::

    logging.getLogger().setLevel(logging.DEBUG)          # root
    logging.getLogger("urllib3").setLevel(logging.DEBUG)
    ... FileHandler("~/.config/colab-cli/colab.log")

``requests_oauthlib`` logs the *entire* token response at DEBUG, so every
authentication appends the access token, the refresh token and the id token to
``colab.log`` in clear text. A refresh token is long-lived, so that file is a standing
credential. There is no CLI flag to turn it off.

Python imports ``sitecustomize`` automatically at interpreter startup when it is
importable, and ``colab.ps1`` puts this directory on ``PYTHONPATH``. Fixing it here
rather than by editing site-packages means ``uv tool upgrade`` cannot silently revert
it. Two independent layers:

1. **Prevent** -- pin the loggers that emit token material to WARNING. ``setup_logging``
   only ever calls ``setLevel`` on the root logger and on ``urllib3``, so these
   settings survive it; the records are never created.
2. **Redact** -- attach a filter to every logging handler that rewrites anything
   resembling a credential. Defends against a future CLI version logging tokens from a
   logger not named below.
"""

import logging
import os
import re
import subprocess
import sys

_NOISY_CREDENTIAL_LOGGERS = (
    "requests_oauthlib",
    "requests_oauthlib.oauth2_session",
    "oauthlib",
    "google_auth_oauthlib",
    "google.auth",
    "urllib3.connectionpool",
)

for _name in _NOISY_CREDENTIAL_LOGGERS:
    logging.getLogger(_name).setLevel(logging.WARNING)

# Cheap pre-check: only run the regexes when a record could plausibly carry a secret.
_TRIGGERS = ("token", "secret", "Authorization", "code=", "ya29", "1//", "Bearer", "code_verifier")

_PATTERNS = [
    # JSON: "access_token": "...."
    re.compile(r'("(?:access|refresh|id)_token"\s*:\s*")[^"]+(")'),
    re.compile(r'("client_secret"\s*:\s*")[^"]+(")'),
    # Form-encoded: code_verifier=..., code=..., client_secret=...
    re.compile(r'\b((?:code_verifier|client_secret|refresh_token|code)=)[^&\s\'"]+'),
    # Headers: 'Authorization': 'Basic xxx' / Bearer xxx
    re.compile(r"((?:Basic|Bearer)\s+)[A-Za-z0-9\-._~+/=]{8,}"),
    # Bare Google token shapes.
    re.compile(r"\bya29\.[A-Za-z0-9\-._~+/=]+"),
    re.compile(r"\b1//[A-Za-z0-9\-._~+/=]{10,}"),
]

_REDACTED = "<redacted>"


def _scrub(text):
    for pattern in _PATTERNS:
        if pattern.groups == 2:
            text = pattern.sub(lambda m: m.group(1) + _REDACTED + m.group(2), text)
        elif pattern.groups == 1:
            text = pattern.sub(lambda m: m.group(1) + _REDACTED, text)
        else:
            text = pattern.sub(_REDACTED, text)
    return text


class _RedactingFilter(logging.Filter):
    """Rewrites the record in place so *every* handler sees the scrubbed text."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:                                    # noqa: BLE001 - never break logging
            return True
        if any(trigger in message for trigger in _TRIGGERS):
            record.msg = _scrub(message)
            record.args = ()
        return True


_original_handler_init = logging.Handler.__init__


def _patched_handler_init(self, *args, **kwargs):
    _original_handler_init(self, *args, **kwargs)
    try:
        self.addFilter(_RedactingFilter())
    except Exception:                                        # noqa: BLE001
        pass


if not getattr(logging.Handler.__init__, "_colab_redaction_patch", False):
    _patched_handler_init._colab_redaction_patch = True
    logging.Handler.__init__ = _patched_handler_init


# --------------------------------------------------------------------------
# 3. Keep the keep-alive daemon out of sight on Windows.
#
# `colab new` spawns a detached daemon that pings the VM so Colab does not
# reclaim it. `commands/session.py::spawn_keep_alive` launches it with
# DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP; because `python.exe` is a
# console-subsystem binary, DETACHED_PROCESS makes Windows give it a *fresh*
# console -- an empty black window that sits there for the life of the session.
# Adding CREATE_NO_WINDOW does not help: Windows ignores that flag when
# DETACHED_PROCESS is set. Running the daemon under `pythonw.exe` (the GUI-
# subsystem build) is the fix that actually works -- it has no console at all.
# The daemon's stdout/stderr/stdin are already DEVNULL, so it loses nothing.
# --------------------------------------------------------------------------

if sys.platform == "win32":
    _original_popen_init = subprocess.Popen.__init__

    def _patched_popen_init(self, args, *rest, **kwargs):
        try:
            if (isinstance(args, (list, tuple)) and args
                    and "keep-alive" in args
                    and str(args[0]).lower().endswith("python.exe")):
                windowless = str(args[0])[: -len("python.exe")] + "pythonw.exe"
                if os.path.exists(windowless):
                    args = [windowless, *args[1:]]
        except Exception:                                    # noqa: BLE001 - never block a spawn
            pass
        _original_popen_init(self, args, *rest, **kwargs)

    if not getattr(subprocess.Popen.__init__, "_colab_windowless_patch", False):
        _patched_popen_init._colab_windowless_patch = True
        subprocess.Popen.__init__ = _patched_popen_init
