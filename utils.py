# utils.py
import ctypes
import winsound


def force_korean_ime(widget):
    """Windows IME를 강제로 한글 입력 모드로 전환하는 함수"""
    try:
        hwnd = int(widget.winId())
        imm32 = ctypes.windll.imm32
        himc = imm32.ImmGetContext(hwnd)
        if himc:
            imm32.ImmSetConversionStatus(himc, 0x0001, 0x0000)
            imm32.ImmReleaseContext(hwnd, himc)
    except Exception:
        pass


def play_beep_success():
    """바코드 인식 성공 시 : 맑고 경쾌한 높은 톤 비프음 (2000Hz, 0.1초)"""
    try:
        winsound.Beep(2000, 100)
    except Exception:
        pass


def play_beep_error():
    """바코드 인식 실패 / 오류 시 : 낮고 무거운 경고 비프음 (450Hz, 0.3초)"""
    try:
        winsound.Beep(450, 300)
    except Exception:
        pass