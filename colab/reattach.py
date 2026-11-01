"""Re-bind a live Colab runtime to a local session name.

Why this exists: on a transient websocket failure the CLI's exec error path calls
``state.prune_session(name)``, which deletes the local name -> runtime mapping.  The VM
survives -- it is still listed by ``colab sessions`` -- but it now shows as ``[?]`` and
the CLI can only address a runtime *by name*, so it becomes unreachable: no exec, no
download, and no ``stop`` either, so it keeps holding the GPU until Colab reclaims it.

The mapping is fully recoverable, because ``list_assignments()`` returns the runtime
proxy token and url alongside the endpoint -- the same three fields ``new`` stores.  So
this rebuilds the SessionState from the server listing instead of creating a VM.

Usage (from this directory):
    uv run --python 3.12 --with google-colab-cli python reattach.py --name flows
    uv run --python 3.12 --with google-colab-cli python reattach.py --name flows --endpoint <id>

With one live runtime and one missing name, no arguments beyond --name are needed.
"""

import argparse
import sys

from colab_cli.common import state
from colab_cli.state import SessionState


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="flows", help="local session name to bind")
    parser.add_argument("--endpoint", default=None,
                        help="runtime endpoint; required only if several are live")
    args = parser.parse_args()

    assignments = state.client.list_assignments()
    if not assignments:
        raise SystemExit("no live runtimes on the server -- nothing to re-attach")

    known = {s.endpoint for s in state.store.list().values()}
    orphans = [a for a in assignments if a.endpoint not in known]

    print(f"{len(assignments)} live runtime(s), {len(orphans)} without a local name:")
    for a in assignments:
        tag = "orphan" if a.endpoint in {o.endpoint for o in orphans} else "named"
        print(f"  [{tag}] {a.endpoint}  {a.accelerator.value}  {a.variant.name}")

    if args.endpoint:
        chosen = next((a for a in assignments if a.endpoint == args.endpoint), None)
        if chosen is None:
            raise SystemExit(f"endpoint {args.endpoint} is not live")
    elif len(orphans) == 1:
        chosen = orphans[0]
    else:
        raise SystemExit(
            f"{len(orphans)} orphaned runtimes -- pass --endpoint to say which one"
        )

    existing = state.store.get(args.name)
    if existing and existing.endpoint != chosen.endpoint:
        raise SystemExit(
            f"'{args.name}' is already bound to {existing.endpoint}; "
            "pick another name rather than overwriting a live mapping"
        )

    state.store.add(SessionState(
        name=args.name,
        token=chosen.runtime_proxy_info.token,
        url=chosen.runtime_proxy_info.url,
        endpoint=chosen.endpoint,
        variant=chosen.variant.name,
        accelerator=chosen.accelerator.value,
    ))
    print(f"\nbound '{args.name}' -> {chosen.endpoint}")
    print("verify with:  .\\colab.ps1 sessions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
