"""Structured commands for an agent or a human terminal."""

import argparse
import json
import sys

from .engine import Engine, WorkgraphError


def main():
    parser = argparse.ArgumentParser(description="Experimental version control for agent work")
    parser.add_argument("--repo", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("status")
    begin = commands.add_parser("begin")
    begin.add_argument("intent")
    begin.add_argument("--session", default="local")
    fork = commands.add_parser("fork")
    fork.add_argument("revision")
    fork.add_argument("--session", default="local")
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("attempt")
    snapshot.add_argument("summary")
    resume = commands.add_parser("resume")
    resume.add_argument("attempt")
    compose = commands.add_parser("compose")
    compose.add_argument("revisions", nargs="+")
    configure = commands.add_parser("set-check", help="Operator: configure a required named check")
    configure.add_argument("name")
    configure.add_argument("argv", nargs=argparse.REMAINDER)
    verify = commands.add_parser("verify")
    verify.add_argument("candidate")
    verify.add_argument("check")
    verify.add_argument("--timeout", type=float, default=60)
    for name in ("inspect", "land"):
        command = commands.add_parser(name)
        command.add_argument("candidate")
    args = parser.parse_args()
    try:
        engine = Engine(args.repo)
        match args.command:
            case "init": result = engine.init()
            case "status": result = engine.status()
            case "begin": result = engine.begin(args.intent, args.session)
            case "fork": result = engine.begin("Alternative attempt", args.session, from_revision=args.revision)
            case "snapshot": result = engine.snapshot(args.attempt, args.summary)
            case "resume": result = engine.resume(args.attempt)
            case "compose": result = engine.compose(args.revisions)
            case "set-check":
                argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
                result = engine.set_check(args.name, argv)
            case "verify": result = engine.verify(args.candidate, args.check, args.timeout)
            case "inspect": result = engine.inspect(args.candidate)
            case "land": result = engine.land(args.candidate)
        print(json.dumps(result, indent=2))
    except WorkgraphError as error:
        print(json.dumps({"error": error.code, "message": str(error)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
