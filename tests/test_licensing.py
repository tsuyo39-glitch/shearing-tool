import base64
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from core.licensing import (LicenseError, hwid_from_uuid, install_license,
                            parse_time, signature_padding, verify_bytes, verify_file)
from tools.license_issuer import make_license, public_bytes


class LicenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.pem = public_bytes(cls.key)
        cls.hwid = 'a' * 64
        cls.now = datetime.now(timezone.utc).replace(microsecond=0)
        cls.start = cls.now - timedelta(hours=1)
        cls.end = cls.now + timedelta(days=1)
        cls.data = make_license(cls.key, cls.hwid, cls.end, cls.start)

    def check(self, data=None, **kwargs):
        return verify_bytes(self.data if data is None else data, self.pem, self.hwid,
                            now=kwargs.get('now', self.now))

    def signed_payload(self, payload):
        raw = json.dumps(payload).encode('utf-8')
        sig = self.key.sign(raw, signature_padding(), hashes.SHA256())
        return json.dumps(dict(payload=base64.b64encode(raw).decode(), signature=base64.b64encode(sig).decode())).encode()

    def test_success_offline(self):
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            self.assertEqual(self.check()['hwid'], self.hwid)

    def test_expiration_boundaries(self):
        self.check(now=self.start)
        self.check(now=self.end - timedelta(microseconds=1))
        for now in (self.end, self.end + timedelta(seconds=1), self.start - timedelta(seconds=1)):
            with self.subTest(now=now), self.assertRaises(LicenseError):
                self.check(now=now)

    def test_other_pc(self):
        with self.assertRaisesRegex(LicenseError, '別のPC'):
            verify_bytes(self.data, self.pem, 'b' * 64, self.now)

    def test_other_signer(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        with self.assertRaisesRegex(LicenseError, '署名'):
            self.check(make_license(key, self.hwid, self.end, self.start))

    def test_tampering(self):
        envelope = json.loads(self.data)
        payload = json.loads(base64.b64decode(envelope['payload']))
        for field, value in [('hwid', 'b'*64), ('expires_at', '2099-01-01T00:00:00+00:00')]:
            changed = dict(payload, **{field: value})
            tampered = dict(envelope, payload=base64.b64encode(json.dumps(changed).encode()).decode())
            with self.subTest(field=field), self.assertRaisesRegex(LicenseError, '署名'):
                self.check(json.dumps(tampered).encode())

    def test_malformed_signed_fields(self):
        payload = self.check()
        for field, value in [('version', True), ('version', 3), ('product', 'other'),
                             ('hwid', None), ('expires_at', '2027-01-01'),
                             ('expires_at', self.start.isoformat()), ('issued_at', 1)]:
            with self.subTest(field=field, value=value), self.assertRaises(LicenseError):
                self.check(self.signed_payload(dict(payload, **{field: value})))

    def test_invalid_files(self):
        for data in (b'', b'{', b'[]', b'null', b'X'*16385,
                     b'{"payload":"***","signature":"x"}',
                     b'{"payload":"a","payload":"b","signature":"x"}'):
            with self.subTest(data=data[:30]), self.assertRaises(LicenseError):
                self.check(data)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(LicenseError):
                verify_file(Path(tmp)/'missing.dat', self.pem, self.hwid)

    def test_atomic_install_and_rejected_import_preserve_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp)/'new.dat', Path(tmp)/'license.dat'
            source.write_bytes(self.data)
            target.write_bytes(b'previous license')
            with patch('core.licensing.os.replace', side_effect=PermissionError('locked')):
                with self.assertRaises(LicenseError):
                    install_license(source, target, self.pem, self.hwid)
            self.assertEqual(target.read_bytes(), b'previous license')
            self.assertFalse(list(Path(tmp).glob('*.tmp')))
            source.write_bytes(b'broken')
            with self.assertRaises(LicenseError):
                install_license(source, target, self.pem, self.hwid)
            self.assertEqual(target.read_bytes(), b'previous license')
            source.write_bytes(self.data)
            install_license(source, target, self.pem, self.hwid)
            self.assertEqual(target.read_bytes(), self.data)
            install_license(target, target, self.pem, self.hwid)

    def test_hwid_normalization_and_invalid(self):
        self.assertEqual(hwid_from_uuid('ABCDEF00-1234-5678-9ABC-123456789ABC'),
                         hwid_from_uuid(' abcdef00-1234-5678-9abc-123456789abc '))
        for value in ('bad', '00000000-0000-0000-0000-000000000000', 'ffffffff-ffff-ffff-ffff-ffffffffffff'):
            with self.assertRaises(ValueError): hwid_from_uuid(value)

    def test_issue_validation(self):
        for hwid, expiry in [('bad', self.end), (self.hwid, self.start), (self.hwid, datetime(2027, 1, 1))]:
            with self.assertRaises(ValueError): make_license(self.key, hwid, expiry, self.now)
        with self.assertRaises(ValueError): parse_time('2027-01-01T00:00:00')

    def test_perpetual_no_clock_dependency(self):
        data = make_license(self.key, self.hwid, now=self.start)
        for current in (datetime(2000, 1, 1, tzinfo=timezone.utc), datetime(2100, 1, 1, tzinfo=timezone.utc)):
            result = self.check(data, now=current)
            self.assertEqual(result['version'], 2)
            self.assertIsNone(result['expires_at'])
        with self.assertRaisesRegex(LicenseError, '別のPC'):
            verify_bytes(data, self.pem, 'b'*64, self.now)

    def test_perpetual_cannot_be_created_by_tampering(self):
        envelope = json.loads(self.data)
        payload = self.check()
        payload.update(version=2, expires_at=None)
        envelope['payload'] = base64.b64encode(json.dumps(payload).encode()).decode()
        with self.assertRaisesRegex(LicenseError, '署名'):
            self.check(json.dumps(envelope).encode())

    def test_strict_version_expiry_pair(self):
        for version, expiry in [(1, None), (2, self.end.isoformat()), (2, ''), (2, False)]:
            payload = dict(self.check(), version=version, expires_at=expiry)
            with self.subTest(version=version, expiry=expiry), self.assertRaises(LicenseError):
                self.check(self.signed_payload(payload))

    def test_issuer_cli_without_expiry(self):
        import io
        from tools.license_issuer import main
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'license.dat'
            with patch('sys.argv', ['license_issuer.py', 'issue', '--hwid', self.hwid, '--out', str(target)]), \
                 patch('tools.license_issuer.load_key', return_value=self.key), \
                 patch('core.license_public_key.PUBLIC_KEY_PEM', self.pem), patch('sys.stdout', new_callable=io.StringIO):
                main()
            self.assertIsNone(verify_file(target, self.pem, self.hwid)['expires_at'])


class GateTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_valid_license_skips_dialog(self):
        from license_gate import require_license
        payload = {'expires_at': '2027-01-01T00:00:00+00:00'}
        with patch('license_gate.get_hwid', return_value='a'*64), patch('license_gate.verify_file', return_value=payload):
            self.assertEqual(require_license(self.root, Path('.')), payload)

    def test_hwid_failure_denies_startup(self):
        from license_gate import require_license
        with patch('license_gate.get_hwid', side_effect=LicenseError('HWID error')), patch('license_gate.messagebox.showerror'):
            self.assertIsNone(require_license(self.root, Path('.')))

    def test_gate_cancel_buttons_and_successful_import(self):
        import tkinter as tk
        from license_gate import require_license
        errors = []
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        for success in (False, True):
            def interact():
                window = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
                try:
                    for size in ('760x340', '640x320'):
                        window.geometry(size)
                        self.root.update()
                        for widget in descendants(window):
                            if widget.winfo_class() in ('Button', 'TButton'):
                                self.assertGreater(widget.winfo_height(), 10)
                                self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(), window.winfo_rooty()+window.winfo_height())
                                self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(), window.winfo_rootx()+window.winfo_width())
                    if success:
                        next(w for w in descendants(window) if w.winfo_class() == 'Button').invoke()
                    else:
                        window.destroy()
                except Exception as exc:
                    errors.append(exc)
                    window.destroy()
            self.root.after(50, interact)
            with patch('license_gate.get_hwid', return_value='a'*64), patch('license_gate.verify_file', side_effect=LicenseError('未登録')), \
                 patch('license_gate.filedialog.askopenfilename', return_value='new.dat'), patch('license_gate.install_license', return_value={'valid': True}):
                result = require_license(self.root, Path('.'))
            self.assertEqual(result, {'valid': True} if success else None)
        if errors: raise errors[0]
