from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QComboBox,
    QCheckBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt

class JobListDialog(QDialog):
    def __init__(self, df, currently_selected, parent=None, is_store_mode=False):
        super().__init__(parent)
        self.setWindowTitle("작업 목록 선택 (목록지정)")
        self.resize(720, 560)
        self.setStyleSheet("font-size: 14px;")
        
        self.df = df
        self.selected_jobs = set(currently_selected)
        self.is_store_mode = is_store_mode
        self.filter_mode = 'STORE' if is_store_mode else 'DELIVERY'
        
        layout = QVBoxLayout(self)
        
        # ★ [모드별 목록 분리 필터 버튼 바]
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 4)
        
        self.btn_f_delivery = QPushButton("📦 납품용 목록")
        self.btn_f_delivery.setCheckable(True)
        self.btn_f_store = QPushButton("🏪 매장재고 목록")
        self.btn_f_store.setCheckable(True)
        self.btn_f_all = QPushButton("🌐 전체 목록")
        self.btn_f_all.setCheckable(True)
        
        self.btn_f_delivery.clicked.connect(lambda: self._set_filter('DELIVERY'))
        self.btn_f_store.clicked.connect(lambda: self._set_filter('STORE'))
        self.btn_f_all.clicked.connect(lambda: self._set_filter('ALL'))
        
        filter_layout.addWidget(self.btn_f_delivery)
        filter_layout.addWidget(self.btn_f_store)
        filter_layout.addWidget(self.btn_f_all)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        top_layout = QHBoxLayout()
        self.btn_all = QPushButton("전체선택")
        self.btn_none = QPushButton("전체취소")
        
        self.line_search = QLineEdit()
        self.line_search.setPlaceholderText("단어검색...")
        self.line_search.textChanged.connect(self.filter_jobs)
        
        self.btn_ok = QPushButton("확 인")
        self.btn_ok.setStyleSheet("background-color: #007ACC; color: white; font-weight: bold; padding: 6px 16px;")
        self.btn_ok.clicked.connect(self._on_accept)
        
        self.btn_cancel = QPushButton("닫 기")
        self.btn_cancel.setStyleSheet("padding: 6px 12px;")
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

        self._update_filter_buttons()
        self.populate_jobs()

    def _sync_selected_from_table(self):
        """현재 화면에 렌더링된 체크박스 상태를 self.selected_jobs와 완벽 동기화"""
        for r in range(self.table.rowCount()):
            check_item = self.table.item(r, 2)
            job_item = self.table.item(r, 1)
            if check_item and job_item:
                job_key = job_item.data(Qt.ItemDataRole.UserRole)
                if job_key:
                    if check_item.checkState() == Qt.CheckState.Checked:
                        self.selected_jobs.add(job_key)
                    else:
                        self.selected_jobs.discard(job_key)

    def _set_filter(self, mode):
        self._sync_selected_from_table()
        self.filter_mode = mode
        self._update_filter_buttons()
        self.populate_jobs()
        if hasattr(self, 'line_search') and self.line_search.text().strip():
            self.filter_jobs(self.line_search.text())

    def _update_filter_buttons(self):
        active_style = "font-size: 13px; font-weight: bold; padding: 6px 14px; background-color: #007ACC; color: white; border-radius: 4px;"
        inactive_style = "font-size: 13px; font-weight: bold; padding: 6px 14px; background-color: #ECEFF1; color: #37474F; border-radius: 4px;"
        
        self.btn_f_delivery.setChecked(self.filter_mode == 'DELIVERY')
        self.btn_f_delivery.setStyleSheet(active_style if self.filter_mode == 'DELIVERY' else inactive_style)
        
        self.btn_f_store.setChecked(self.filter_mode == 'STORE')
        self.btn_f_store.setStyleSheet(active_style if self.filter_mode == 'STORE' else inactive_style)
        
        self.btn_f_all.setChecked(self.filter_mode == 'ALL')
        self.btn_f_all.setStyleSheet(active_style if self.filter_mode == 'ALL' else inactive_style)
        
    def populate_jobs(self):
        self.table.clear()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["등록일자", "작업목록", "선택"])

        if self.df.empty:
            self.table.setRowCount(0)
            return

        cols = ['등록일자', '등록일시', '거래처', '납품처', '내용']
        for c in cols:
            if c not in self.df.columns:
                self.df[c] = ""
                
        batch_cols = ['등록일자', '등록일시', '거래처', '납품처']
        unique_batches = self.df[batch_cols].drop_duplicates().copy()

        # 유효한 거래처 및 납품처만 엄격 선별 (헤더명 및 공백/nan 필터링)
        v_client = unique_batches['거래처'].astype(str).str.strip()
        v_deliv = unique_batches['납품처'].astype(str).str.strip()
        valid_mask = (v_client != '') & (v_client.str.lower() != 'nan') & (v_client != '거래처') & \
                     (v_deliv != '') & (v_deliv.str.lower() != 'nan')
        unique_batches = unique_batches[valid_mask].copy()

        # ★ 납품용 vs 매장재고 모드별 분리 필터링
        deliv_clean = unique_batches['납품처'].astype(str).str.strip()
        if self.filter_mode == 'DELIVERY':
            unique_batches = unique_batches[deliv_clean != '매장재고'].copy()
        elif self.filter_mode == 'STORE':
            unique_batches = unique_batches[deliv_clean == '매장재고'].copy()
        
        # ★ [핵심 버그 수정] 반드시 0부터 시작하는 연속 인덱스로 재정렬하여 빈 행 생성 원천 차단!
        unique_batches = unique_batches.reset_index(drop=True)
        total_rows = len(unique_batches)
        self.table.setRowCount(total_rows)

        if total_rows == 0:
            return
        
        for r_idx, row in unique_batches.iterrows():
            reg_date = str(row['등록일자']).strip()
            reg_dt = str(row['등록일시']).strip()
            if not reg_date or reg_date.lower() == 'nan':
                reg_date = datetime.now().strftime("%Y-%m-%d")
                
            client = str(row['거래처']).strip()
            delivery = str(row['납품처']).strip()
            
            mask = (self.df['거래처'].astype(str).str.strip() == client) & \
                   (self.df['납품처'].astype(str).str.strip() == delivery) & \
                   (self.df['등록일시'].astype(str).str.strip() == reg_dt)
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
                
            self.table.setItem(r_idx, 0, item_date)
            self.table.setItem(r_idx, 1, item_job)
            self.table.setItem(r_idx, 2, item_check)
            
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

    def _on_accept(self):
        self._sync_selected_from_table()
        self.accept()
                
    def get_selected_jobs(self):
        self._sync_selected_from_table()
        return set(self.selected_jobs)


class BookEditDialog(QDialog):
    def __init__(self, row_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("도서 정보 개별 수정 (유통 공급/판매가 관리)")
        self.resize(480, 560)
        self.setStyleSheet("font-size: 15px;")
        
        layout = QFormLayout(self)
        layout.setSpacing(10)
        
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
        
        price_str = str(row_data.get('정가', '0')).replace(',', '').strip()
        try:
            init_price = int(float(price_str)) if price_str else 0
        except Exception:
            init_price = 0
        self.line_price = QLineEdit(str(init_price))
        
        # 1. 공급율 (%)
        rate_str = str(row_data.get('공급율', '')).replace('%', '').strip()
        try:
            init_rate = float(rate_str) if rate_str else 70.0
        except Exception:
            init_rate = 70.0
        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.0, 100.0)
        self.spin_rate.setDecimals(1)
        self.spin_rate.setSingleStep(1.0)
        self.spin_rate.setValue(init_rate)
        self.spin_rate.setSuffix(" %")
        self.spin_rate.setStyleSheet("padding: 5px;")
        
        # 2. 공급가 (원)
        sup_price_str = str(row_data.get('공급가', '')).replace(',', '').strip()
        try:
            init_sup_price = int(float(sup_price_str)) if sup_price_str and float(sup_price_str) > 0 else int(init_price * init_rate / 100.0)
        except Exception:
            init_sup_price = int(init_price * init_rate / 100.0)
        self.line_supply_price = QLineEdit(str(init_sup_price) if init_sup_price > 0 else "")
        
        # 3. 10% 할인 토글 및 판매가 (원)
        self.cb_discount = QCheckBox("정가 대비 10% 할인 판매 (해제 시 정가)")
        sale_price_str = str(row_data.get('판매가', '')).replace(',', '').strip()
        try:
            init_sale_price = int(float(sale_price_str)) if sale_price_str and float(sale_price_str) > 0 else int(init_price * 0.9)
        except Exception:
            init_sale_price = int(init_price * 0.9)
            
        if init_price > 0 and init_sale_price == init_price:
            self.cb_discount.setChecked(False)
        else:
            self.cb_discount.setChecked(True)
            
        self.line_sale_price = QLineEdit(str(init_sale_price) if init_sale_price > 0 else "")
        
        for le in [self.line_client, self.line_delivery, self.line_content, self.line_isbn, 
                   self.line_title, self.line_author, self.line_publisher, self.line_price, 
                   self.line_supply_price, self.line_sale_price]:
            le.setStyleSheet("padding: 5px; border: 1px solid #ccc; border-radius: 4px;")
        
        layout.addRow("상 태 :", self.combo_status)
        layout.addRow("거래처(공급처) :", self.line_client)
        layout.addRow("납품처 :", self.line_delivery)
        layout.addRow("내 용 :", self.line_content)
        layout.addRow("ISBN :", self.line_isbn)
        layout.addRow("도서명 :", self.line_title)
        layout.addRow("저 자 :", self.line_author)
        layout.addRow("출판사 :", self.line_publisher)
        layout.addRow("정 가 (원) :", self.line_price)
        layout.addRow("공급율 (%) :", self.spin_rate)
        layout.addRow("공급가 (원) :", self.line_supply_price)
        layout.addRow("", self.cb_discount)
        layout.addRow("판매가 (원) :", self.line_sale_price)
        
        # 시그널 연결 (자동 계산)
        self.line_price.textChanged.connect(self._recalc_prices)
        self.spin_rate.valueChanged.connect(self._recalc_prices)
        self.cb_discount.toggled.connect(self._recalc_prices)
        
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("저장 및 적용"); btn_save.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("취소"); btn_cancel.setStyleSheet("background-color: #F44336; color: white; font-weight: bold; padding: 10px;")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_save); btn_layout.addWidget(btn_cancel)
        layout.addRow(btn_layout)

    def _recalc_prices(self):
        try:
            p_val = self.line_price.text().strip().replace(',', '')
            price = int(float(p_val)) if p_val else 0
        except Exception:
            price = 0
            
        rate = self.spin_rate.value()
        calc_sup = int(price * (rate / 100.0))
        self.line_supply_price.setText(str(calc_sup))
        
        if self.cb_discount.isChecked():
            calc_sale = int(price * 0.9)
        else:
            calc_sale = price
        self.line_sale_price.setText(str(calc_sale))
        
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
            '정가': self.line_price.text().strip(),
            '공급율': f"{self.spin_rate.value():.1f}",
            '공급가': self.line_supply_price.text().strip(),
            '판매가': self.line_sale_price.text().strip()
        }
