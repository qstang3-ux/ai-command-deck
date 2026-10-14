import argparse
import sys
from .storage import Store


def main():
    parser = argparse.ArgumentParser(description='AI Command Deck · 本机只读终端实时查看与回放')
    parser.add_argument('--data-dir', help='Private local session directory')
    parser.add_argument('--retention-days', type=int, help='Retention after session end (default: 7 days)')
    sub = parser.add_subparsers(dest='mode', required=True)
    server = sub.add_parser('serve', help='Start loopback-only viewer')
    server.add_argument('--port', type=int, default=8768)
    run = sub.add_parser('run', help='Record an authorized command through a real PTY')
    run.add_argument('--name', default=None)
    run.add_argument('command', nargs=argparse.REMAINDER)
    sub.add_parser('cleanup', help='Remove only expired, inactive sessions')
    args = parser.parse_args()
    try:
        store = Store(args.data_dir, args.retention_days)
    except ValueError as exc:
        parser.error(str(exc))
    if args.mode == 'serve':
        from .server import serve
        serve(store, args.port)
    elif args.mode == 'cleanup':
        print(f'Removed {len(store.cleanup())} expired sessions')
    else:
        command = args.command
        if command and command[0] == '--':
            command = command[1:]
        if not command:
            parser.error('run requires a command, e.g. -- ssh user@server')
        from .recorder import record
        sys.exit(record(store, command, args.name))


if __name__ == '__main__':
    main()
