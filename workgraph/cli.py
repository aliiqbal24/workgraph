"""Workgraph command line entry point."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

from .engine import Engine, WorkgraphError
from .version import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explore saved project versions and continue durable work across agents")
    parser.add_argument("--repo", default=".", help="Repository path (default: current directory)")
    parser.add_argument("--version", action="version", version="Workgraph " + __version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "status", "doctor", "recover"):
        commands.add_parser(name)
    begin = commands.add_parser("begin", help="Open work and an isolated attempt")
    begin.add_argument("intent")
    begin.add_argument("--session", default="local")
    begin.add_argument("--runtime", default="local")
    begin.add_argument("--depends-on", action="append", default=[])
    begin.add_argument("--constraint", action="append", default=[])
    begin.add_argument("--request-id")
    fork = commands.add_parser("fork")
    fork.add_argument("revision")
    fork.add_argument("--session", default="alternative")
    fork.add_argument("--runtime", default="local")
    snapshot = commands.add_parser("snapshot", aliases=["checkpoint"])
    snapshot.add_argument("attempt")
    snapshot.add_argument("summary", nargs="?")
    snapshot.add_argument("--decision", action="append")
    snapshot.add_argument("--next", action="append", dest="plan")
    snapshot.add_argument("--question", action="append")
    snapshot.add_argument("--select", action="store_true", default=None)
    snapshot.add_argument("--request-id")
    for name in ("resume", "reconcile"):
        command = commands.add_parser(name)
        command.add_argument("attempt")
    takeover = commands.add_parser("takeover")
    takeover.add_argument("attempt")
    takeover.add_argument("--session", required=True)
    takeover.add_argument("--runtime", default="local")
    state = commands.add_parser("state")
    state.add_argument("attempt")
    state.add_argument("state", choices=["active", "paused", "interrupted", "finished", "abandoned"])
    select = commands.add_parser("select")
    select.add_argument("revision")
    compose = commands.add_parser("compose")
    compose.add_argument("revisions", nargs="+")
    compose.add_argument("--request-id")
    configure = commands.add_parser("set-check", help="Operator: configure a required check")
    configure.add_argument("name")
    configure.add_argument("--trusted-file", action="append", default=[])
    verify = commands.add_parser("verify")
    verify.add_argument("candidate")
    verify.add_argument("check")
    verify.add_argument("--timeout", type=float, default=60)
    verify.add_argument("--request-id")
    for name in ("inspect", "land"):
        command = commands.add_parser(name)
        command.add_argument("candidate")
        command.add_argument("--request-id")
    diff = commands.add_parser("diff")
    diff.add_argument("--revision")
    diff.add_argument("--candidate")
    server = commands.add_parser("serve", help="Open the private local operator UI")
    server.add_argument("--port", type=int, default=8731)
    example = commands.add_parser("demo", help="Create and serve the real guided example")
    example.add_argument("--directory")
    example.add_argument("--port", type=int, default=8731)
    example.add_argument("--complete", action="store_true", help="Run all example operations without a browser")
    playground = commands.add_parser("playground", help="Explore a real website with saved versions and alternative directions")
    playground.add_argument("--directory")
    playground.add_argument("--port",type=int,default=8731)
    mcp = commands.add_parser("mcp", help="Serve shared agent tools over stdio")
    mcp.add_argument("--session")
    mcp.add_argument("--runtime", default="mcp")
    mcp.add_argument("--attempt")
    hook = commands.add_parser("hook")
    hook.add_argument("event")
    setup = commands.add_parser("hook-config", help="Print optional lifecycle config for review/trust")
    setup.add_argument("runtime", choices=["codex", "claude"])
    launch = commands.add_parser("launch", help="Launch an existing agent in a managed workspace")
    launch.add_argument("runtime", choices=["hermes", "codex", "claude"])
    launch.add_argument("--intent")
    launch.add_argument("--attempt")
    launch.add_argument("--print", action="store_true", dest="print_only")
    raw = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw:
        divider = raw.index("--")
        raw, tail = raw[:divider], raw[divider + 1:]
    else:
        tail = []
    args = parser.parse_args(raw)
    if tail and args.command not in ("launch", "set-check"):
        parser.error("Arguments after -- are supported only by launch and set-check.")
    try:
        if args.command == "playground":
            from .playground import Playground
            from .server import serve
            engine=Playground.create(args.directory or tempfile.mkdtemp(prefix="workgraph-playground-"))
            serve(engine.repo,args.port)
            return
        elif args.command == "demo":
            from .example import Example
            example = Example.create(args.directory or tempfile.mkdtemp(prefix="workgraph-example-"))
            if args.complete:
                for _ in range(6):
                    example.advance()
                result = {"example": example.state(), "workspace": example.engine.status()}
            else:
                from .server import serve
                serve(example.engine.repo, args.port, example=True)
                return
        elif args.command == "serve":
            from .server import serve
            serve(args.repo, args.port)
            return
        elif args.command == "mcp":
            from .mcp import serve
            serve(args.repo, args.session, args.runtime, args.attempt)
            return
        elif args.command == "hook":
            from .hooks import run
            result = run(args.event)
        elif args.command == "hook-config":
            from .hooks import configuration
            result = configuration(args.runtime)
        elif args.command == "launch":
            from .launch import launch
            result = launch(args.repo, args.runtime, args.intent, args.attempt, tail, args.print_only)
        else:
            engine = Engine(args.repo)
            match args.command:
                case "init": result = engine.init()
                case "status": result = engine.status()
                case "doctor":
                    from .doctor import inspect
                    result = inspect(args.repo)
                case "recover": result = engine.recover()
                case "begin": result = engine.begin(args.intent, args.session, runtime=args.runtime, depends_on=args.depends_on,
                                                     constraints=args.constraint, request_id=args.request_id)
                case "fork": result = engine.begin("Alternative attempt", args.session, runtime=args.runtime, from_revision=args.revision)
                case "snapshot" | "checkpoint": result = engine.checkpoint(args.attempt, args.summary, decisions=args.decision,
                    plan=args.plan, questions=args.question, select=args.select, request_id=args.request_id)
                case "resume": result = engine.resume(args.attempt)
                case "takeover": result = engine.takeover(args.attempt, args.session, args.runtime)
                case "reconcile": result = engine.reconcile(args.attempt)
                case "state": result = engine.transition(args.attempt, args.state)
                case "select": result = engine.select(args.revision)
                case "compose": result = engine.compose(args.revisions, args.request_id)
                case "set-check":
                    if not tail:
                        raise WorkgraphError("MISSING_COMMAND", "Provide the check command after --.")
                    result = engine.set_check(args.name, tail, trusted_files=args.trusted_file)
                case "verify": result = engine.verify(args.candidate, args.check, args.timeout, args.request_id)
                case "inspect": result = engine.inspect(args.candidate)
                case "land": result = engine.land(args.candidate, args.request_id)
                case "diff": result = engine.diff(args.revision, args.candidate)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.command == "launch" and not args.print_only:
            return result.get("exit_code",0)
    except WorkgraphError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False))
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
