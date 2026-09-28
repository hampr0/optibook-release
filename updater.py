import os
import sys
import json
import urllib.request
import tempfile
import subprocess
import re
from PyQt6.QtWidgets import QMessageBox, QProgressDialog
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# 깃허브 저장소 정보
GITHUB_REPO = "hampr0/optibook-release"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

def parse_version(ver_str):
    """버전 문자열을 숫자 튜플로 변환 (예: 'v1.0.2' -> [1, 0, 2])"""
    clean_ver = re.sub(r'[^\d.]', '', ver_str)
    return [int(x) for x in clean_ver.split('.') if x.isdigit()]

class DownloadThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, download_url, save_path):
        super().__init__()
        self.download_url = download_url
        self.save_path = save_path

    def run(self):
        try:
            req = urllib.request.Request(
                self.download_url, 
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req) as response:
                total_size = int(response.info().get('Content-Length', 0))
                downloaded = 0
                block_size = 8192

                with open(self.save_path, 'wb') as f:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        downloaded += len(buffer)
                        f.write(buffer)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress.emit(percent)

            self.finished.emit(self.save_path)
        except Exception as e:
            self.error.emit(str(e))

def check_and_run_update(current_version, parent=None):
    """최신 버전 체크 및 자동 업데이트 실행 함수"""
    try:
        req = urllib.request.Request(
            LATEST_RELEASE_API, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            
        latest_tag = data.get('tag_name', '')
        if not latest_tag:
            return

        cur_v = parse_version(current_version)
        lat_v = parse_version(latest_tag)

        # 최신 버전이 더 높은 경우에만 업데이트 실행
        if lat_v > cur_v:
            # Setup.exe 에셋 링크 찾기
            download_url = None
            file_name = "Optibook_Setup.exe"
            for asset in data.get('assets', []):
                if asset.get('name', '').endswith('.exe'):
                    download_url = asset.get('browser_download_url')
                    file_name = asset.get('name')
                    break

            if not download_url:
                return

            body_notes = data.get('body', '성능 개선 및 버그 수정')
            reply = QMessageBox.question(
                parent,
                "새 버전 업데이트 알림",
                f"최신 버전 [{latest_tag}]이 출시되었습니다!\n(현재 버전: v{current_version})\n\n"
                f"[업데이트 내용]\n{body_notes}\n\n"
                "지금 다운로드하여 업데이트를 진행하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )

            if reply == QMessageBox.StandardButton.Yes:
                temp_dir = tempfile.gettempdir()
                save_path = os.path.join(temp_dir, file_name)

                # 다운로드 진행률 다이얼로그
                progress_dlg = QProgressDialog("최신 업데이트 설치 파일을 다운로드 중입니다...", "취소", 0, 100, parent)
                progress_dlg.setWindowTitle("업데이트 다운로드")
                progress_dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
                progress_dlg.setAutoClose(False)
                progress_dlg.show()

                downloader = DownloadThread(download_url, save_path)
                downloader.progress.connect(progress_dlg.setValue)

                def on_finished(installer_path):
                    progress_dlg.close()
                    QMessageBox.information(
                        parent, 
                        "설치 시작", 
                        "다운로드가 완료되었습니다.\n업데이트 설치를 시작하며 프로그램을 종료합니다."
                    )
                    # 인스톨러 실행 후 현재 프로그램 완전 종료
                    subprocess.Popen([installer_path], shell=True)
                    sys.exit(0)

                def on_error(err_msg):
                    progress_dlg.close()
                    QMessageBox.warning(parent, "업데이트 실패", f"다운로드 중 오류가 발생했습니다:\n{err_msg}")

                downloader.finished.connect(on_finished)
                downloader.error.connect(on_error)
                downloader.start()

                # 다운로드 끝날 때까지 대기
                while downloader.isRunning():
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()

    except Exception:
        # 인터넷 연결 불안정이나 GitHub API 지연 시 프로그램 시작이 막히지 않도록 조용히 넘어감
        pass