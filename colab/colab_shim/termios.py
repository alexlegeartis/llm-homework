"""Windows stub for the Unix-only ``termios`` module.

``google-colab-cli`` is documented as Linux/macOS only, but the *only* thing that
actually breaks on Windows is an unconditional ``import termios`` (and ``tty``) in
``colab_cli/console.py``, which ``colab_cli/commands/execution.py`` imports at module
load. Both are used solely inside ``connect_console()`` -- the interactive raw-TTY
``colab console`` command.

Every command this project needs -- ``new``, ``exec``, ``run``, ``stop``, ``download``,
``install``, ``log`` -- is HTTP/websocket based and never touches them. Putting this
directory on ``PYTHONPATH`` therefore makes the CLI importable on Windows without
patching the installed package (so ``uv tool upgrade`` cannot silently revert it).

Calling any function here raises, rather than silently misbehaving: on Windows the
interactive console genuinely is unavailable.
"""

TCSANOW = 0
TCSADRAIN = 1
TCSAFLUSH = 2

_MESSAGE = (
    "The interactive `colab console` / `colab repl` TTY is not available on Windows "
    "(no termios). Use `colab exec -f <file>` or `colab run <script>` instead."
)


def _unsupported(*_args, **_kwargs):
    raise NotImplementedError(_MESSAGE)


tcgetattr = _unsupported
tcsetattr = _unsupported
tcdrain = _unsupported
tcflush = _unsupported
tcsendbreak = _unsupported


class error(Exception):
    """Mirrors ``termios.error`` so ``except termios.error`` still parses."""
