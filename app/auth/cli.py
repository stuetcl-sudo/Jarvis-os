import argparse
import getpass
import sys

from app.auth.service import ALLOWED_ROLES, auth_service, initialize_auth_tables


def prompt_password():
    first = getpass.getpass("Adgangskode: ")
    second = getpass.getpass("Gentag adgangskode: ")
    if first != second:
        raise ValueError("Passwords do not match")
    return first


def build_parser():
    parser = argparse.ArgumentParser(description="Administrer lokale Jarvis-os brugere")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="Opret en lokal bruger")
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", required=True)
    create.add_argument("--role", required=True, choices=sorted(ALLOWED_ROLES))

    commands.add_parser("list-users", help="Vis lokale brugere")

    disable = commands.add_parser("disable-user", help="Deaktivér en bruger")
    disable.add_argument("--username", required=True)

    enable = commands.add_parser("enable-user", help="Aktivér en bruger")
    enable.add_argument("--username", required=True)

    reset = commands.add_parser("reset-password", help="Nulstil en brugers adgangskode")
    reset.add_argument("--username", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    initialize_auth_tables()
    try:
        if args.command == "create-user":
            user = auth_service.create_user(args.username, args.display_name, args.role, prompt_password())
            print(f"Oprettet: {user['username']} ({user['role']})")
        elif args.command == "list-users":
            for user in auth_service.list_users():
                state = "disabled" if user["disabled"] else "enabled"
                print(f"{user['username']}\t{user['display_name']}\t{user['role']}\t{state}")
        elif args.command == "disable-user":
            user = auth_service.set_user_disabled(args.username, True)
            print(f"Deaktiveret: {user['username']}")
        elif args.command == "enable-user":
            user = auth_service.set_user_disabled(args.username, False)
            print(f"Aktiveret: {user['username']}")
        elif args.command == "reset-password":
            user = auth_service.reset_password(args.username, prompt_password())
            print(f"Adgangskode nulstillet: {user['username']}")
    except ValueError as exc:
        print(f"Fejl: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
