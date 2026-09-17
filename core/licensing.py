"""Offline RSA-PSS license verification. No network access or private keys."""
import base64
import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

PRODUCT = 'shearing-tool'
MAX_LICENSE_BYTES = 16384


class LicenseError(Exception):
    pass


def signature_padding():
    return padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError('日時は文字列で指定してください。')
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('日時にはタイムゾーンが必要です。')
    return result.astimezone(timezone.utc)


def hwid_from_uuid(value):
    identifier = uuid.UUID(str(value).strip())
    if identifier.int in (0, (1 << 128) - 1):
        raise ValueError('システムUUIDが無効です。')
    return hashlib.sha256(f'{PRODUCT}:hwid-v1:{identifier}'.encode('utf-8')).hexdigest()


def get_hwid():
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            locator = win32com.client.Dispatch('WbemScripting.SWbemLocator')
            service = locator.ConnectServer('.', r'root\cimv2')
            rows = list(service.ExecQuery('SELECT UUID FROM Win32_ComputerSystemProduct'))
            if len(rows) != 1:
                raise ValueError('システムUUIDが一意に取得できません。')
            value = str(rows[0].UUID)
            del rows, service, locator
            return hwid_from_uuid(value)
        finally:
            pythoncom.CoUninitialize()
    except Exception as exc:
        raise LicenseError('このPCのHWIDを取得できません。WindowsのWMI設定を確認してください。') from exc


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('JSONキーが重複しています。')
        result[key] = value
    return result


def decode_json(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)


def read_license(path):
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_LICENSE_BYTES + 1)
        if len(data) > MAX_LICENSE_BYTES:
            raise LicenseError('ライセンスファイルが大きすぎます。')
        return data
    except FileNotFoundError as exc:
        raise LicenseError('ライセンスが未登録です。license.datを読み込んでください。') from exc
    except OSError as exc:
        raise LicenseError('ライセンスファイルを読み込めません。') from exc


def verify_bytes(data, public_pem, hwid, now=None):
    try:
        if len(data) > MAX_LICENSE_BYTES:
            raise ValueError('ファイルサイズ超過')
        envelope = decode_json(data)
        if not isinstance(envelope, dict) or set(envelope) != {'payload', 'signature'}:
            raise ValueError('外部形式が不正')
        payload_bytes = base64.b64decode(envelope['payload'], validate=True)
        signature = base64.b64decode(envelope['signature'], validate=True)
        key = serialization.load_pem_public_key(public_pem)
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 3072:
            raise ValueError('公開鍵が不正')
        key.verify(signature, payload_bytes, signature_padding(), hashes.SHA256())
        payload = decode_json(payload_bytes)
        fields = {'version', 'product', 'hwid', 'issued_at', 'expires_at'}
        if not isinstance(payload, dict) or set(payload) != fields:
            raise ValueError('署名対象の形式が不正')
        if type(payload['version']) is not int or payload['version'] not in (1, 2) or payload['product'] != PRODUCT:
            raise LicenseError('このアプリ用のライセンスではありません。')
        if not isinstance(payload['hwid'], str) or not re.fullmatch('[0-9a-f]{64}', payload['hwid']):
            raise ValueError('HWID形式が不正')
        if payload['hwid'] != hwid:
            raise LicenseError('別のPCに発行されたライセンスです。')
        issued = parse_time(payload['issued_at'])
        if payload['version'] == 2:
            # Version 2 explicitly means perpetual. Version 1 remains time-limited.
            if payload['expires_at'] is not None:
                raise ValueError('無期限ライセンスの形式が不正')
            return payload
        expires = parse_time(payload['expires_at'])
        if expires <= issued:
            raise ValueError('有効期間が不正')
        current = now if now is not None else datetime.now(timezone.utc)
        if current < issued:
            raise LicenseError('PCの日時がライセンス発行日時より前です。日時を確認してください。')
        if current >= expires:
            raise LicenseError('ライセンスの有効期限が切れています。')
        return payload
    except LicenseError:
        raise
    except InvalidSignature as exc:
        raise LicenseError('署名が一致しません。改ざん、または発行元が異なります。') from exc
    except Exception as exc:
        raise LicenseError('ライセンスの形式または公開鍵が不正です。') from exc


def verify_file(path, public_pem, hwid):
    return verify_bytes(read_license(path), public_pem, hwid)


def install_license(source, destination, public_pem, hwid):
    """Validate exact bytes before atomically replacing an existing license."""
    data = read_license(source)
    payload = verify_bytes(data, public_pem, hwid)
    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.license-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        raise LicenseError('ライセンスを保存できません。EXEのフォルダーへの書込権限を確認してください。') from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return payload
