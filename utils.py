# utils.py
import ctypes
import threading
try:
    import winsound
except ImportError:
    winsound = None


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
    """바코드 인식 성공 시 : 맑고 경쾌한 높은 톤 비프음 (2000Hz, 0.1초 - 비동기 스레드 실행으로 UI 멈춤 방지)"""
    if winsound is None:
        return
    def _beep():
        try:
            winsound.Beep(2000, 100)
        except Exception:
            pass
    threading.Thread(target=_beep, daemon=True).start()


def play_beep_error():
    """바코드 인식 실패 / 오류 시 : 낮고 무거운 경고 비프음 (450Hz, 0.3초 - 비동기 스레드 실행으로 UI 멈춤 방지)"""
    if winsound is None:
        return
    def _beep():
        try:
            winsound.Beep(450, 300)
        except Exception:
            pass
    threading.Thread(target=_beep, daemon=True).start()


def apply_combobox_style(combo, font_size="13px"):
    """
    모든 QComboBox 및 QFontComboBox의 드롭다운(팝업) 목록 배경을
    불투명한 순백색(#FFFFFF)으로 강제 지정하여 투명화 현상을 원천 방지하고,
    선명한 텍스트와 파란색 선택 하이라이트를 적용합니다.
    """
    qss = f"""
    QComboBox, QFontComboBox {{
        background-color: #FFFFFF;
        color: #0F172A;
        border: 1px solid #94A3B8;
        border-radius: 5px;
        padding: 5px 10px;
        font-size: {font_size};
        font-weight: bold;
        min-height: 26px;
    }}
    QComboBox:hover, QFontComboBox:hover {{
        border: 1px solid #007ACC;
    }}
    QComboBox::drop-down, QFontComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 26px;
        border-left: 1px solid #CBD5E1;
        background-color: #F1F5F9;
        border-top-right-radius: 5px;
        border-bottom-right-radius: 5px;
    }}
    QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {{
        background-color: #FFFFFF;
        color: #0F172A;
        selection-background-color: #007ACC;
        selection-color: #FFFFFF;
        border: 1px solid #64748B;
        border-radius: 4px;
        outline: 0px;
        padding: 4px;
    }}
    QComboBox QAbstractItemView::item, QFontComboBox QAbstractItemView::item {{
        min-height: 30px;
        padding: 5px 10px;
        color: #0F172A;
        background-color: #FFFFFF;
    }}
    QComboBox QAbstractItemView::item:hover, QFontComboBox QAbstractItemView::item:hover {{
        background-color: #E0F2FE;
        color: #0369A1;
    }}
    QComboBox QAbstractItemView::item:selected, QFontComboBox QAbstractItemView::item:selected {{
        background-color: #007ACC;
        color: #FFFFFF;
    }}
    """
    combo.setStyleSheet(qss)
    try:
        view = combo.view()
        if view:
            view.setStyleSheet(
                "background-color: #FFFFFF; color: #0F172A; selection-background-color: #007ACC; selection-color: #FFFFFF; border: 1px solid #64748B;"
            )
            view.setAutoFillBackground(True)
    except Exception:
        pass
