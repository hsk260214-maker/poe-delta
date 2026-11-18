"""즉시 저장하는 거래소 설정과 명시적 API 위험 확인."""
import time

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton)

from trade import config, secret

RISK_TEXT = (
    "이 방식은 GGG 개발자 문서에 없는 거래소 내부 API를 사용합니다.\n"
    "공식 문서는 이를 약관 위반으로 적고 있으며 계정 정지 위험이 있습니다.\n"
    "Awakened PoE Trade 등도 같은 방식이지만 GGG는 허용을 보장하지 않습니다.\n"
    "사용에 따른 위험은 사용자 계정이 부담합니다."
)


def confirm_api(parent=None) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle("게임 위 시세 모드 위험 안내")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(RISK_TEXT)
    accept = box.addButton("위험을 이해하고 사용", QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    box.exec()
    return box.clickedButton() is accept


class SettingsDialog(QDialog):
    def __init__(self, parent=None, lang: str = "en"):
        super().__init__(parent)
        self.setWindowTitle("거래소 설정")
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        trade = config.settings()
        self.mode = QComboBox()
        self.mode.addItem("브라우저 모드 (기본)", "browser")
        self.mode.addItem("게임 위 시세 모드", "api")
        self.mode.setCurrentIndex(1 if config.mode() == "api" else 0)
        form.addRow("검색 방식", self.mode)
        self.server = QComboBox()
        self.server.addItem("공식", config.OFFICIAL)
        if lang == "ko" and config.KAKAO_ENABLED:
            self.server.addItem("카카오", config.KAKAO)
        self.server.setCurrentIndex(max(0, self.server.findData(trade.get("server", config.OFFICIAL))))
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
        requested = self.mode.currentData()
        if requested == "api" and config.mode() != "api":
            if not confirm_api(self):
                self.mode.blockSignals(True)
                self.mode.setCurrentIndex(0)
                self.mode.blockSignals(False)
                self._enable_api_fields()
                return
            config.save(mode="api", api_ack_at=time.time())
        else:
            config.save(mode=requested)
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
