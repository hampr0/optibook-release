from utils import apply_combobox_style
import traceback
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QComboBox,
    QCheckBox, QDoubleSpinBox, QMessageBox
)
from PyQt6.QtCore import Qt

class JobListDialog(QDialog):
    def __init__(self, df, currently_selected, parent=None, is_store_mode=False, *args, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("작업 목록 선택 (목록지정)")
        self.resize(720, 560)
        self.setStyleSheet("font-size: 14px;")
        
        self.df = df
        self.selected_jobs = set(currently_selected) if currently_selected else set()
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
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 115)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 65)
        layout.addWidget(self.table)
        
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.btn_all.clicked.connect(self.select_all)
        self.btn_none.clicked.connect(self.select_none)

        self._update_filter_buttons()
        self.populate_jobs()

    def _on_cell_clicked(self, row, col):
        if col != 2:
            item = self.table.item(row, 2)
            if item:
                new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
                item.setCheckState(new_state)

    def _sync_selected_from_table(self):
        """현재 화면에 렌더링된 체크박스 상태를 self.selected_jobs와 완벽 동기화"""
        try:
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
        except Exception as e:
            print(f"체크박스 동기화 오류: {e}")

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
        self.table.setUpdatesEnabled(False)
        try:
            self.table.clear()
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["등록일자", "작업목록", "선택"])

            if self.df is None or self.df.empty:
                self.table.setRowCount(0)
                return

            # 1. 대상 컬럼 안전 추출 및 전처리 (대용량 2만 건 0초 고속 캐싱)
            cols = ['등록일자', '등록일시', '거래처', '납품처', '내용']
            sub_cols = [c for c in cols if c in self.df.columns]
            view_df = self.df[sub_cols].copy()
            for c in cols:
                if c not in view_df.columns:
                    view_df[c] = ""
                else:
                    view_df[c] = view_df[c].astype(str).str.strip()

            # 2. 배치별 '내용' 집계 맵 사전 생성 (루프 내 2만 건 전체 순회 완전 제거)
            content_summary = {}
            for (c, d, rdt), grp in view_df.groupby(['거래처', '납품처', '등록일시']):
                contents = [x for x in grp['내용'].unique() if x and x not in ['nan', 'None', '내용']]
                if len(contents) == 1:
                    content_summary[(c, d, rdt)] = f" ({contents[0]})"
                elif len(contents) > 1:
                    content_summary[(c, d, rdt)] = f" ({contents[0]} 외 {len(contents)-1}종)"
                else:
                    content_summary[(c, d, rdt)] = ""

            # 3. 고유 작업 배치 목록 추출
            ub = view_df[['등록일자', '등록일시', '거래처', '납품처']].drop_duplicates().copy()

            # 유효 거래처/납품처 선별
            valid_mask = (ub['거래처'] != '') & (ub['거래처'].str.lower() != 'nan') & (ub['거래처'] != '거래처') & \
                         (ub['납품처'] != '') & (ub['납품처'].str.lower() != 'nan')
            ub = ub[valid_mask].copy()

            # 모드별 필터링
            if self.filter_mode == 'DELIVERY':
                ub = ub[ub['납품처'] != '매장재고'].copy()
            elif self.filter_mode == 'STORE':
                ub = ub[ub['납품처'] == '매장재고'].copy()
            
            ub = ub.reset_index(drop=True)
            total_rows = len(ub)
            self.table.setRowCount(total_rows)

            if total_rows == 0:
                return
            
            for r_idx, row in ub.iterrows():
                client = row['거래처']
                delivery = row['납품처']
                reg_dt = row['등록일시']
                reg_date = row['등록일자']
                if not reg_date or reg_date.lower() == 'nan':
                    reg_date = datetime.now().strftime("%Y-%m-%d")
                    
                cnt_str = content_summary.get((client, delivery, reg_dt), "")
                time_tag = f" [{reg_dt[11:16]}]" if len(reg_dt) >= 16 else ""
                job_str = f"[{client}]{delivery}{cnt_str}{time_tag}"
                job_key = (client, delivery, reg_dt) if reg_dt else (client, delivery)
                
                # 안전한 플래그 설정 (Bitwise XOR 연산 제거로 PyQt6 타입 오류 완벽 차단)
                item_date = QTableWidgetItem(reg_date)
                item_date.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                
                item_job = QTableWidgetItem(job_str)
                item_job.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item_job.setData(Qt.ItemDataRole.UserRole, job_key)
                
                item_check = QTableWidgetItem()
                item_check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
                
                is_checked = False
                for sel in self.selected_jobs:
                    if isinstance(sel, (tuple, list)):
                        if len(sel) == 3 and (sel[0], sel[1], sel[2]) == (client, delivery, reg_dt):
                            is_checked = True; break
                        elif len(sel) == 2 and (sel[0], sel[1]) == (client, delivery):
                            is_checked = True; break
                        elif len(sel) >= 4 and (sel[0], sel[1]) == (client, delivery) and sel[-1] == reg_dt:
                            is_checked = True; break

                item_check.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
                    
                self.table.setItem(r_idx, 0, item_date)
                self.table.setItem(r_idx, 1, item_job)
                self.table.setItem(r_idx, 2, item_check)
        except Exception as e:
            print(f"목록 생성 중 오류: {e}")
            traceback.print_exc()
        finally:
            self.table.setUpdatesEnabled(True)
            
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
        apply_combobox_style(self.combo_status, font_size="14px")
        
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

        delivery_str = str(row_data.get('납품처', '')).strip()
        is_store = (delivery_str == '매장재고')
        
        # 1. 공급율 (%) - 매장재고 도서만 기본 70% 적용, 납품 도서는 0% 공란 비활성화
        rate_str = str(row_data.get('공급율', '')).replace('%', '').strip()
        if is_store:
            try: init_rate = float(rate_str) if rate_str else 70.0
            except Exception: init_rate = 70.0
        else:
            init_rate = 0.0

        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.0, 100.0)
        self.spin_rate.setDecimals(1)
        self.spin_rate.setSingleStep(1.0)
        self.spin_rate.setValue(init_rate)
        self.spin_rate.setSuffix(" %")
        self.spin_rate.setStyleSheet("padding: 5px;")
        
        # 2. 공급가 (원)
        sup_price_str = str(row_data.get('공급가', '')).replace(',', '').strip()
        if is_store:
            try:
                init_sup_price = int(float(sup_price_str)) if sup_price_str and float(sup_price_str) > 0 else int(init_price * init_rate / 100.0)
            except Exception:
                init_sup_price = int(init_price * init_rate / 100.0)
        else:
            init_sup_price = 0
        self.line_supply_price = QLineEdit(str(init_sup_price) if (is_store and init_sup_price > 0) else "")
        
        # 3. 10% 할인 토글 및 판매가 (원)
        self.cb_discount = QCheckBox("정가 대비 10% 할인 판매 (해제 시 정가)")
        sale_price_str = str(row_data.get('판매가', '')).replace(',', '').strip()
        if is_store:
            try:
                init_sale_price = int(float(sale_price_str)) if sale_price_str and float(sale_price_str) > 0 else int(init_price * 0.9)
            except Exception:
                init_sale_price = int(init_price * 0.9)
                
            if init_price > 0 and init_sale_price == init_price:
                self.cb_discount.setChecked(False)
            else:
                self.cb_discount.setChecked(True)
        else:
            init_sale_price = 0
            self.cb_discount.setChecked(False)
            
        self.line_sale_price = QLineEdit(str(init_sale_price) if (is_store and init_sale_price > 0) else "")
        
        self._update_store_fields_visibility(is_store)
        self.line_delivery.textChanged.connect(lambda: self._update_store_fields_visibility(self.line_delivery.text().strip() == '매장재고'))
        
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

    def _update_store_fields_visibility(self, is_store):
        self.spin_rate.setEnabled(is_store)
        self.line_supply_price.setEnabled(is_store)
        self.cb_discount.setEnabled(is_store)
        self.line_sale_price.setEnabled(is_store)
        if not is_store:
            self.spin_rate.setValue(0.0)
            self.line_supply_price.setText("")
            self.line_supply_price.setPlaceholderText("납품용 도서 (해당없음)")
            self.line_sale_price.setText("")
            self.line_sale_price.setPlaceholderText("납품용 도서 (해당없음)")
        else:
            self.line_supply_price.setPlaceholderText("")
            self.line_sale_price.setPlaceholderText("")
            self._recalc_prices()

    def _recalc_prices(self):
        if self.line_delivery.text().strip() != '매장재고':
            self.line_supply_price.setText("")
            self.line_sale_price.setText("")
            return

        try:
            p_val = self.line_price.text().strip().replace(',', '')
            price = int(float(p_val)) if p_val else 0
        except Exception:
            price = 0
            
        rate = self.spin_rate.value()
        calc_sup = int(price * (rate / 100.0))
        self.line_supply_price.setText(str(calc_sup) if calc_sup > 0 else "")
        
        if self.cb_discount.isChecked():
            calc_sale = int(price * 0.9)
        else:
            calc_sale = price
        self.line_sale_price.setText(str(calc_sale) if calc_sale > 0 else "")
        
    def get_data(self):
        is_store = (self.line_delivery.text().strip() == '매장재고')
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
            '공급율': f"{self.spin_rate.value():.1f}" if is_store else '',
            '공급가': self.line_supply_price.text().strip() if is_store else '',
            '판매가': self.line_sale_price.text().strip() if is_store else ''
        }
