"""Developer-only issuer. Never bundle this file or the signing key."""
import argparse
import base64
import getpass
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from core.licensing import PRODUCT, get_hwid, signature_padding

KEY_DIRECTORY = Path.home() / '.shearing-tool-signing'
KEY_PATH = KEY_DIRECTORY / 'private_key.dpapi'
PUBLIC_PATH = Path(__file__).resolve().parents[1] / 'core' / 'license_public_key.py'


def public_bytes(key):
    return key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def load_key():
    import win32crypt
    decrypted = win32crypt.CryptUnprotectData(KEY_PATH.read_bytes(), None, None, None, 0)[1]
    key = serialization.load_pem_private_key(decrypted, password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 3072:
        raise ValueError('RSA 3072ビット以上の秘密鍵が必要です。')
    return key


def initialize():
    import win32crypt
    if PUBLIC_PATH.exists():
        raise ValueError('公開鍵が存在します。既存の鍵を上書きしません。')
    if KEY_PATH.exists():
        key = load_key()  # recover if public-file creation was interrupted
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        raw = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        encrypted = win32crypt.CryptProtectData(raw, 'shearing-tool signing key', None, None, None, 0)
        KEY_DIRECTORY.mkdir(parents=True, exist_ok=True)
        with KEY_PATH.open('xb') as stream:
            stream.write(encrypted)
    with PUBLIC_PATH.open('x', encoding='utf-8') as stream:
        stream.write('# Public verification key only. Do not replace after distribution.\n')
        stream.write(f'PUBLIC_KEY_PEM = {public_bytes(key)!r}\n')
    print(f'Private key (Windows DPAPI): {KEY_PATH}')
    print(f'Public key: {PUBLIC_PATH}')


def make_license(key, hwid, expires=None, now=None):
    hwid = hwid.strip().lower()
    if not re.fullmatch('[0-9a-f]{64}', hwid):
        raise ValueError('HWIDは64文字の16進数で指定してください。')
    issued = now if now is not None else datetime.now(timezone.utc)
    if issued.tzinfo is None:
        raise ValueError('発行日時にはタイムゾーンが必要です。')
    if expires is not None and (expires.tzinfo is None or expires <= issued):
        raise ValueError('期限はタイムゾーン付きの未来日時を指定してください。')
    payload = dict(version=2 if expires is None else 1, product=PRODUCT, hwid=hwid,
                   issued_at=issued.astimezone(timezone.utc).isoformat(),
                   expires_at=None if expires is None else expires.astimezone(timezone.utc).isoformat())
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    signature = key.sign(raw, signature_padding(), hashes.SHA256())
    return json.dumps(dict(payload=base64.b64encode(raw).decode('ascii'),
                           signature=base64.b64encode(signature).decode('ascii')), indent=2).encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description='オフラインライセンス発行（開発者専用）')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    sub.add_parser('hwid')
    issue = sub.add_parser('issue')
    issue.add_argument('--hwid', required=True)
    issue.add_argument('--out', required=True)
    export = sub.add_parser('export-key', help='別PCへ復元できるパスワード付き秘密鍵バックアップ')
    export.add_argument('--out', required=True)
    restore = sub.add_parser('import-key', help='パスワード付き秘密鍵をこのWindowsユーザーへ復元')
    restore.add_argument('--file', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'init':
            initialize()
        elif args.command == 'hwid':
            print(get_hwid())
        elif args.command == 'import-key':
            import win32crypt
            from core.license_public_key import PUBLIC_KEY_PEM
            password = getpass.getpass('Backup password: ').encode('utf-8')
            key = serialization.load_pem_private_key(Path(args.file).read_bytes(), password=password)
            if not isinstance(key, rsa.RSAPrivateKey) or public_bytes(key) != PUBLIC_KEY_PEM:
                raise ValueError('アプリの公開鍵と一致しません。')
            raw = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            KEY_DIRECTORY.mkdir(parents=True, exist_ok=True)
            with KEY_PATH.open('xb') as stream:
                stream.write(win32crypt.CryptProtectData(raw, 'shearing-tool signing key', None, None, None, 0))
            print('Restored signing key.')
        else:
            key = load_key()
            from core.license_public_key import PUBLIC_KEY_PEM
            if public_bytes(key) != PUBLIC_KEY_PEM:
                raise ValueError('秘密鍵とアプリの公開鍵が一致しません。')
            if args.command == 'issue':
                data = make_license(key, args.hwid)
            else:
                password = getpass.getpass('Backup password (12+ characters): ')
                if len(password) < 12 or password != getpass.getpass('Confirm password: '):
                    raise ValueError('12文字以上の一致するパスワードが必要です。')
                data = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.BestAvailableEncryption(password.encode('utf-8')))
            with Path(args.out).open('xb') as stream:
                stream.write(data)
            print(f'Created: {args.out}')
    except Exception as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
