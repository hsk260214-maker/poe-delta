"""즉시 저장하는 거래소 설정."""

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton)

from trade import config, secret

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("거래소 설정")
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        trade = config.settings()
        self.mode = QComboBox()
        self.mode.addItem("브라우저 모드", "browser")
        self.mode.addItem("게임 위 시세 모드 (기본)", "api")
        self.mode.setCurrentIndex(1 if config.mode() == "api" else 0)
        form.addRow("검색 방식", self.mode)
        self.server = QComboBox()
        self.server.addItem("공식", config.OFFICIAL)
        if config.KAKAO_ENABLED:
            self.server.addItem("카카오 (한글 클라이언트 전용)", config.KAKAO)
        index = self.server.findData(trade.get("server", config.default_server()))
        if index < 0:
            index = 0
            config.save(server=config.OFFICIAL)
        self.server.setCurrentIndex(index)
        form.addRow("서버", self.server)
        self.league = QLineEdit(trade.get("league", ""))
        self.league.setPlaceholderText("현재 챌린지 리그 이름")
        form.addRow("리그", self.league)
        self.ratio = QDoubleSpinBox()
        self.ratio.setRange(0, 1)
        self.ratio.setSingleStep(0.05)
        self.ratio.setValue(trade.get("min_ratio", 0.9))
        form.addRow("기본 최소값 비율", self.ratio)
        self.hotkey = QCheckBox("Ctrl+D 사용")
        self.hotkey.setChecked(trade.get("hotkey_enabled", True))
        form.addRow("단축키", self.hotkey)
        self.cookie = QLineEdit()
        self.cookie.setEchoMode(QLineEdit.EchoMode.Password)
        self.cookie.setPlaceholderText("변경할 POESESSID 입력 (저장된 값은 표시하지 않음)")
        cookie_row = QHBoxLayout()
        cookie_row.addWidget(self.cookie)
        self.delete = QPushButton("지우기")
        cookie_row.addWidget(self.delete)
        form.addRow("POESESSID", cookie_row)
        self.contact = QLineEdit(trade.get("contact", ""))
        form.addRow("연락처", self.contact)
        form.addRow(QLabel("가판대(즉시 구매) 매물만 검색합니다."))
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        form.addRow(close)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.server.currentIndexChanged.connect(lambda: config.save(server=self.server.currentData()))
        self.league.editingFinished.connect(lambda: config.save(league=self.league.text().strip()))
        self.ratio.valueChanged.connect(lambda value: config.save(min_ratio=value))
        self.hotkey.toggled.connect(lambda value: config.save(hotkey_enabled=value))
        self.contact.editingFinished.connect(lambda: config.save(contact=self.contact.text().strip()))
        self.cookie.editingFinished.connect(self._save_cookie)
        self.delete.clicked.connect(self._delete_cookie)
        self._enable_api_fields()

    def _mode_changed(self) -> None:
        config.save(mode=self.mode.currentData())
        self._enable_api_fields()

    def _enable_api_fields(self) -> None:
        enabled = config.mode() == "api"
        for widget in (self.cookie, self.delete, self.contact):
            widget.setEnabled(enabled)

    def _save_cookie(self) -> None:
        if not self.cookie.text() or config.mode() != "api":
            return
        value = self.cookie.text()
        self.cookie.clear()
        try:
            secret.save_session(value)
        except secret.SecretError as error:
            QMessageBox.warning(self, "거래소 설정", str(error))

    def _delete_cookie(self) -> None:
        self.cookie.clear()
        try:
            secret.delete_session()
        except secret.SecretError as error:
            QMessageBox.warning(self, "거래소 설정", str(error))
