#!/usr/bin/env python3
"""Run interactively on the wrapper host; credentials never enter shell arguments."""
import getpass
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:18080'


def request(path, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(BASE + path, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=90) as response:
            return json.loads(response.read(1024 * 1024))
    except HTTPError as error:
        # Never echo the response: authentication responses can contain tokens.
        raise RuntimeError(f'Wrapper request failed (HTTP {error.code}); no account response displayed') from None


def main():
    if not sys.stdin.isatty():
        raise RuntimeError('Run in an interactive terminal with ssh -t')
    current = request('/me')
    if current.get('auth', {}).get('state') == 'authenticated':
        print('Wrapper is already signed in.')
        return
    print('Sign in to your private wrapper on this server. Inputs are hidden.')
    username = getpass.getpass('Apple ID: ').strip()
    password = getpass.getpass('Apple Music password: ')
    try:
        result = request('/login', {'username': username, 'password': password})
    finally:
        password = None
    if result.get('state') == 'awaiting_2fa':
        code = getpass.getpass('Apple verification code: ').strip()
        try:
            result = request('/login/2fa', {'code': code})
        finally:
            code = None
    if result.get('state') != 'authenticated':
        raise RuntimeError('Sign-in did not complete; no account response displayed')
    print('Sign-in completed. No credentials or session tokens displayed.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        # Network exception details are deliberately suppressed too.
        print(str(error) if isinstance(error, RuntimeError) else 'Sign-in connection failed.', file=sys.stderr)
        raise SystemExit(1)
