"""Windows 사용자별 DPAPI 암호화 저장. 평문을 오류에 포함하지 않는다."""
import ctypes
from ctypes import wintypes

from paths import ROAMING

SESSION_FILE = ROAMING / "trade_session.bin"


class SecretError(Exception):
    def __init__(self):
        super().__init__("거래소 세션을 안전하게 저장하거나 읽지 못했습니다")


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data: bytes, protect: bool) -> bytes:
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if protect:
            function = crypt32.CryptProtectData
            function.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
        else:
            function = crypt32.CryptUnprotectData
            function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
        function.restype = wintypes.BOOL
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
            raise SecretError()
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            kernel32.LocalFree(target.pbData)
    except (OSError, AttributeError):
        raise SecretError() from None


def save_session(value: str) -> None:
    try:
        encrypted = _crypt(value.encode("utf-8"), True)
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_bytes(encrypted)
    except OSError:
        raise SecretError() from None


def load_session() -> str:
    try:
        encrypted = SESSION_FILE.read_bytes()
    except FileNotFoundError:
        return ""
    except OSError:
        raise SecretError() from None
    try:
        return _crypt(encrypted, False).decode("utf-8")
    except UnicodeError:
        raise SecretError() from None


def delete_session() -> None:
    try:
        SESSION_FILE.unlink(missing_ok=True)
    except OSError:
        raise SecretError() from None
