"""Optional Windows-user protected credential profile; no browser/session storage."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path


def profile_path():
    root = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not root:
        raise ValueError("stored profiles require Windows; use environment variables")
    return Path(root) / "JinoCLI" / "credentials.dpapi"


def configured():
    if os.environ.get("JINO_LOGIN") and os.environ.get("JINO_PASSWORD"):
        return True
    return os.name == "nt" and profile_path().is_file()


def crypt(data, *, decrypt=False):
    if os.name != "nt":
        raise ValueError("DPAPI is only available on Windows")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    result = Blob()
    library = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    # Current-user encryption and CRYPTPROTECT_UI_FORBIDDEN. No machine-wide key.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ValueError("Windows could not access the credential profile")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        if result.pbData:
            ctypes.memset(result.pbData, 0, result.cbData)
            kernel.LocalFree(result.pbData)
        ctypes.memset(buffer, 0, len(data))


def load():
    login, password = os.environ.get("JINO_LOGIN"), os.environ.get("JINO_PASSWORD")
    if login or password:
        if not login or not password:
            raise ValueError("set both credential environment variables")
        return login, password
    data = json.loads(crypt(profile_path().read_bytes(), decrypt=True).decode("utf-8"))
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) and data[k] for k in ("login", "password")):
        raise ValueError("invalid credential profile")
    return data["login"], data["password"]


def save(login, password):
    path = profile_path()
    if not login or not password:
        raise ValueError("login and password are required")
    encrypted = crypt(json.dumps({"login": login, "password": password}).encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    # Encrypted data only; replace atomically, including on an existing profile.
    import tempfile
    handle, temporary = tempfile.mkstemp(prefix="credentials-", suffix=".dpapi", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(encrypted)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
