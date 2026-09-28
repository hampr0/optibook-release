from datetime import datetime
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QComboBox
from PyQt6.QtCore import Qt

class JobListDialog(QDialog):
    def __init__(self, df, currently_selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("작업 목록 선택 (목록지정)")
        self.resize(680, 520)
        self.setStyleSheet("font-size: 14px;")
        
        self.df = df
        self.selected_jobs = set(currently_selected)
        
        layout = QVBoxLayout(self)
        top_layout = QHBoxLayout()
        self.btn_all = QPushButton("전체선택")
        self.btn_none = QPushButton("전체취소")
        
        self.line_search = QLineEdit()
        self.line_search.setPlaceholderText("단어검색...")
        self.line_search.textChanged.connect(self.filter_jobs)
        
        self.btn_ok = QPushButton("확 인")
        self.btn_ok.setStyleSheet("background-color: #007ACC; color: white; font-weight: bold;")
        self.btn_ok.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("닫 기")
        self.btn_cancel.clicked.connect(self.reject)
        
        top_layout.addWidget(self.btn_all)
        top_layout.addWidget(self.btn_none)
        top_layout.addWidget(QLabel("검색:"))
        top_layout.addWidget(self.line_search)
        top_layout.addWidget(self.btn_ok)
        top_layout.addWidget(self.btn_cancel)
        layout.addLayout(top_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["등록일자", "작업목록", "선택"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)
        
        self.btn_all.clicked.connect(self.select_all)
        self.btn_none.clicked.connect(self.select_none)
        self.populate_jobs()
        
    def populate_jobs(self):
        if self.df.empty: return
        cols = ['등록일자', '등록일시', '거래처', '납품처', '내용']
        for c in cols:
            if c not in self.df.columns: self.df[c] = ""
                
        batch_cols = ['등록일자', '등록일시', '거래처', '납품처']
        unique_batches = self.df[batch_cols].drop_duplicates().reset_index(drop=True)
        unique_batches = unique_batches[unique_batches['거래처'] != '거래처']
        
        self.table.setRowCount(len(unique_batches))
        
        for i, row in unique_batches.iterrows():
            reg_date = str(row['등록일자']).strip()
            reg_dt = str(row['등록일시']).strip()
            if not reg_date or reg_date.lower() == 'nan':
                reg_date = datetime.now().strftime("%Y-%m-%d")
                
            client = str(row['거래처']).strip()
            delivery = str(row['납품처']).strip()
            
            mask = (self.df['거래처'] == client) & (self.df['납품처'] == delivery) & (self.df['등록일시'] == reg_dt)
            sub_df = self.df[mask]
            
            unique_contents = [c for c in sub_df['내용'].dropna().unique() if str(c).strip() and str(c).strip() != '내용']
            if len(unique_contents) == 1:
                cnt_str = f" ({unique_contents[0]})"
            elif len(unique_contents) > 1:
                cnt_str = f" ({unique_contents[0]} 외 {len(unique_contents)-1}종)"
            else:
                cnt_str = ""
                
            job_key = (client, delivery, reg_dt) if reg_dt else (client, delivery)
            time_tag = f" [{reg_dt[11:16]}]" if len(reg_dt) >= 16 else ""
            job_str = f"[{client}]{delivery}{cnt_str}{time_tag}"
            
            item_date = QTableWidgetItem(reg_date)
            item_date.setFlags(item_date.flags() ^ Qt.ItemFlag.ItemIsEditable)
            
            item_job = QTableWidgetItem(job_str)
            item_job.setFlags(item_job.flags() ^ Qt.ItemFlag.ItemIsEditable)
            item_job.setData(Qt.ItemDataRole.UserRole, job_key)
            
            item_check = QTableWidgetItem()
            item_check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            
            is_checked = False
            for sel in self.selected_jobs:
                if isinstance(sel, tuple):
                    if len(sel) == 3 and sel == (client, delivery, reg_dt): is_checked = True; break
                    elif len(sel) == 2 and sel == (client, delivery): is_checked = True; break
                    elif len(sel) == 4 and sel[:2] == (client, delivery) and sel[3] == reg_dt: is_checked = True; break

            if is_checked:
                item_check.setCheckState(Qt.CheckState.Checked)
            else:
                item_check.setCheckState(Qt.CheckState.Unchecked)
                
            self.table.setItem(i, 0, item_date)
            self.table.setItem(i, 1, item_job)
            self.table.setItem(i, 2, item_check)
            
    def select_all(self):
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                item = self.table.item(r, 2)
                if item: item.setCheckState(Qt.CheckState.Checked)
                    
    def select_none(self):
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                item = self.table.item(r, 2)
                if item: item.setCheckState(Qt.CheckState.Unchecked)
                    
    def filter_jobs(self, text):
        text = text.lower().strip()
        for r in range(self.table.rowCount()):
            job_item = self.table.item(r, 1)
            if job_item:
                job_str = job_item.text().lower()
                self.table.setRowHidden(r, text not in job_str)
                
    def get_selected_jobs(self):
        selected = set()
        for r in range(self.table.rowCount()):
            check_item = self.table.item(r, 2)
            job_item = self.table.item(r, 1)
            if check_item and check_item.checkState() == Qt.CheckState.Checked and job_item:
                job_key = job_item.data(Qt.ItemDataRole.UserRole)
                selected.add(job_key)
        return selected


class BookEditDialog(QDialog):
    def __init__(self, row_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("도서 정보 개별 수정")
        self.resize(450, 420)
        self.setStyleSheet("font-size: 16px;")
        
        layout = QFormLayout(self)
        layout.setSpacing(12)
        
        self.combo_status = QComboBox()
        self.combo_status.addItems(["미입고", "입고", "삭제"])
        self.combo_status.setCurrentText(str(row_data.get('상태', '미입고')))
        self.combo_status.setStyleSheet("padding: 5px;")
        
        self.line_client = QLineEdit(str(row_data.get('거래처', '')))
        self.line_delivery = QLineEdit(str(row_data.get('납품처', '')))
        self.line_content = QLineEdit(str(row_data.get('내용', '')))
        self.line_isbn = QLineEdit(str(row_data.get('ISBN_Clean', '')))
        self.line_title = QLineEdit(str(row_data.get('도서명', '')))
        self.line_author = QLineEdit(str(row_data.get('저자', '')))
        self.line_publisher = QLineEdit(str(row_data.get('출판사', '')))
        self.line_price = QLineEdit(str(row_data.get('정가', ''))) 
        
        for le in [self.line_client, self.line_delivery, self.line_content, self.line_isbn, self.line_title, self.line_author, self.line_publisher, self.line_price]:
            le.setStyleSheet("padding: 5px; border: 1px solid #ccc; border-radius: 4px;")
        
        layout.addRow("상 태 :", self.combo_status)
        layout.addRow("거래처 :", self.line_client)
        layout.addRow("납품처 :", self.line_delivery)
        layout.addRow("내 용 :", self.line_content)
        layout.addRow("ISBN :", self.line_isbn)
        layout.addRow("도서명 :", self.line_title)
        layout.addRow("저 자 :", self.line_author)
        layout.addRow("출판사 :", self.line_publisher)
        layout.addRow("정 가 :", self.line_price)
        
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("저장 및 적용"); btn_save.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("취소"); btn_cancel.setStyleSheet("background-color: #F44336; color: white; font-weight: bold; padding: 10px;")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_save); btn_layout.addWidget(btn_cancel)
        layout.addRow(btn_layout)
        
    def get_data(self):
        return {
            '상태': self.combo_status.currentText(),
            '거래처': self.line_client.text().strip(),
            '납품처': self.line_delivery.text().strip(),
            '내용': self.line_content.text().strip(),
            'ISBN_Clean': self.line_isbn.text().strip(),
            '도서명': self.line_title.text().strip(),
            '저자': self.line_author.text().strip(),
            '출판사': self.line_publisher.text().strip(),
            '정가': self.line_price.text().strip() 
        }
