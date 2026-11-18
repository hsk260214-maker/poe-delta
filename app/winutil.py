"""옵션변경·지도 경고·거래소 창의 공용 Windows 입력 처리."""
import sys


def send_copy_to(hwnd: int) -> bool:
    """hwnd(게임 창)를 앞으로 돌리고 Ctrl+C 를 보낸다. Windows 전용."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd):
            return False
        import os

        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return False  # 이 프로그램 창이면 넘기지 않음 (프로그램 안에서 연 경우)
        kernel32 = ctypes.windll.kernel32
        my_tid = kernel32.GetCurrentThreadId()
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        attached = tid and tid != my_tid and user32.AttachThreadInput(my_tid, tid, True)
        user32.SetForegroundWindow(hwnd)
        if attached:
            user32.AttachThreadInput(my_tid, tid, False)
        return True
    except Exception:  # noqa: BLE001
        return False


def foreground_other() -> int:
    """지금 앞에 있는 창이 다른 프로그램(게임)이면 그 hwnd, 아니면 0."""
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        import os

        user32 = ctypes.windll.user32
        fg = user32.GetForegroundWindow()
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        return fg if fg and pid.value != os.getpid() else 0
    except Exception:  # noqa: BLE001
        return 0


def foreground_window() -> int:
    if sys.platform != "win32":
        return 0
    import ctypes

    get_foreground = ctypes.windll.user32.GetForegroundWindow
    get_foreground.restype = ctypes.c_void_p
    return get_foreground() or 0


def window_exists(hwnd: int) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    import ctypes

    return bool(ctypes.windll.user32.IsWindow(hwnd))


def foreground_category(hwnd: int) -> str:
    if not hwnd:
        return "none"
    if sys.platform != "win32":
        return "other"
    import ctypes
    import os

    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return "poe_delta"
    return "game" if is_poe_window(hwnd) else "other"


def focus_window(hwnd: int, *, allow_alt_fallback: bool = True) -> bool:
    """hwnd 창을 맨 앞 + 키보드 포커스로. 다른 프로그램(게임)이 앞에 있어도 되게 그 창의 입력 스레드에 잠깐 붙어서 넘김."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd):
            return False
        if not allow_alt_fallback:
            return bool(user32.SetForegroundWindow(hwnd)) and foreground_window() == hwnd
        my_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        fg = user32.GetForegroundWindow()
        if fg == hwnd:
            return True
        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        attached = bool(fg_tid and fg_tid != my_tid and user32.AttachThreadInput(my_tid, fg_tid, True))
        try:
            user32.BringWindowToTop(hwnd)
            ok = bool(user32.SetForegroundWindow(hwnd)) and user32.GetForegroundWindow() == hwnd
            if not ok:
                # 포그라운드 잠금 풀기: 이 프로그램이 마지막 입력을 보낸 것으로 만들어야 넘겨줌 (Alt 한 번 톡)
                # (게임이 관리자 권한이면 이것도 막힘 → 이 프로그램도 관리자 권한으로 켜야 함)
                kb = user32.keybd_event
                kb(0x12, 0, 0x0001, 0)
                kb(0x12, 0, 0x0001 | 0x0002, 0)
                ok = bool(user32.SetForegroundWindow(hwnd)) and user32.GetForegroundWindow() == hwnd
        finally:
            if attached:
                user32.AttachThreadInput(my_tid, fg_tid, False)
        return ok
    except Exception:  # noqa: BLE001
        return False


def key_down(vk: int) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        # 0x8000 = 지금 눌림, 0x0001 = 지난 확인 이후 눌린 적 있음 (짧게 톡 누른 것도 잡기)
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8001)
    except Exception:  # noqa: BLE001
        return False


def press_ctrl_c() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kb = ctypes.windll.user32.keybd_event
        VK_CONTROL, VK_C, UP = 0x11, 0x43, 0x0002
        kb(VK_CONTROL, 0x1D, 0, 0)
        kb(VK_C, 0x2E, 0, 0)
        kb(VK_C, 0x2E, UP, 0)
        kb(VK_CONTROL, 0x1D, UP, 0)
    except Exception:  # noqa: BLE001
        pass


def is_poe_window(hwnd: int) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    import ctypes

    name = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, name, len(name))
    return name.value == "POEWindowClass"
