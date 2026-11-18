"""캐릭터 가져오기 다이얼로그: 계정(공개 프로필) / PoB 코드·링크."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from asyncjob import run_async
from char_leagues import league_groups, league_of, league_sort_key
from dialogs import DragHeader, FramelessDialog
from editor import NoWheelCombo
from pob import importers


class ImportDialog(FramelessDialog):
    """accept 되면 self.kind('json'|'xml'), self.payload, self.name, self.source 가 채워진다."""

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.kind = self.payload = self.name = None
        self.source: dict = {}
        self._account = ""
        self._busy = False
        self._league_choice: str | None = None
        self.resize(720, 560)

        v = QVBoxLayout(self.frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        header = DragHeader()
        hh = QHBoxLayout(header)
        hh.setContentsMargins(18, 0, 0, 0)
        t = QLabel("캐릭터 가져오기")
        t.setObjectName("DialogTitle")
        hh.addWidget(t)
        hh.addStretch(1)
        close = QToolButton()
        close.setObjectName("WinClose")
        close.setText("")
        close.setFixedSize(46, 40)
        close.clicked.connect(self.reject)
        hh.addWidget(close)
        v.addWidget(header)

        body = QVBoxLayout()
        body.setContentsMargins(20, 16, 20, 16)
        body.setSpacing(12)
        v.addLayout(body, 1)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.mode = QButtonGroup(self)
        for i, label in enumerate(["계정에서 가져오기", "PoB 코드 / 링크"]):
            b = QPushButton(label)
            b.setObjectName("FilterChip")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.mode.addButton(b, i)
            chips.addWidget(b)
        chips.addStretch(1)
        body.addLayout(chips)

        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        self.pages.addWidget(self._account_page())
        self.pages.addWidget(self._code_page())
        self.mode.idClicked.connect(self._set_mode)

        self.status = QLabel("")
        self.status.setObjectName("DialogSub")
        self.status.setWordWrap(True)
        body.addWidget(self.status)

        bh = QHBoxLayout()
        bh.addStretch(1)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        self.ok_btn = QPushButton("가져오기")
        self.ok_btn.setObjectName("Primary")
        self.ok_btn.clicked.connect(self._do_import)
        bh.addWidget(cancel)
        bh.addWidget(self.ok_btn)
        body.addLayout(bh)

        mode = int(settings.get("import_mode", 0))
        self.mode.button(mode).setChecked(True)
        self._set_mode(mode)

    # ---- 페이지 ----
    def _account_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.realm = NoWheelCombo()
        for label, code in importers.REALMS:
            self.realm.addItem(label, code)
        self.realm.setCurrentIndex(max(0, self.realm.findData(self.settings.get("realm", "pc"))))
        self.realm.setFixedWidth(130)
        self.account = QLineEdit(self.settings.get("account", ""))
        self.account.setPlaceholderText("계정 이름  (예: Exile#1234)")
        self.account.returnPressed.connect(self._load_list)
        self.list_btn = QPushButton("캐릭터 목록")
        self.list_btn.clicked.connect(self._load_list)
        row.addWidget(self.realm)
        row.addWidget(self.account, 1)
        row.addWidget(self.list_btn)
        v.addLayout(row)
        self.league_group = QButtonGroup(self)
        self.league_group.setExclusive(True)
        self.league_group.buttonClicked.connect(
            lambda button: self._filter_league(button.property("league"), remember=True))
        league_strip = QWidget()
        self.league_layout = QHBoxLayout(league_strip)
        self.league_layout.setContentsMargins(0, 0, 0, 0)
        self.league_layout.setSpacing(6)
        self.league_scroll = QScrollArea()
        self.league_scroll.setWidgetResizable(True)
        self.league_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.league_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.league_scroll.setFixedHeight(54)
        self.league_scroll.setWidget(league_strip)
        v.addWidget(self.league_scroll)
        self.char_list = QListWidget()
        self.char_list.setObjectName("ResultList")
        self.char_list.itemDoubleClicked.connect(lambda _: self._do_import())
        v.addWidget(self.char_list, 1)
        hint = QLabel(
            "pathofexile.com 공개 프로필에서 가져옵니다 (PoB 의 계정 가져오기와 같은 방식).\n"
            "프로필 → Privacy Settings 에서 Characters 탭을 공개로 설정해야 합니다."
        )
        hint.setObjectName("SectionLabel")
        v.addWidget(hint)
        return w

    def _code_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.code = QPlainTextEdit()
        self.code.setPlaceholderText(
            "PoB 에서 Import/Export Build → Generate 로 만든 코드를 붙여넣거나\n"
            "pobb.in · pastebin · poe.ninja · pob.codes · maxroll 링크를 붙여넣으세요."
        )
        v.addWidget(self.code, 1)
        self.code_name = QLineEdit()
        self.code_name.setPlaceholderText("캐릭터 이름 (비워두면 자동)")
        v.addWidget(self.code_name)
        return w

    def _set_mode(self, i: int) -> None:
        self.pages.setCurrentIndex(i)
        self.settings["import_mode"] = i
        self._set_status("")

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.setText(text)
        self.status.setStyleSheet("color: #ff8f78;" if error else "")

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._busy = busy
        self.ok_btn.setEnabled(not busy)
        self.list_btn.setEnabled(not busy)
        if text:
            self._set_status(text)

    # ---- 계정 ----
    def _load_list(self) -> None:
        name = self.account.text().strip()
        if not name or self._busy:
            if not name:
                self._set_status("계정 이름을 입력하세요.", True)
            return
        realm = self.realm.currentData()
        self.settings.update(account=name, realm=realm)
        self._set_busy(True, "캐릭터 목록 받는 중…")
        run_async(lambda: importers.list_characters(name, realm), self._on_list, self._on_err)

    def _on_list(self, res) -> None:
        self._set_busy(False)
        self._account, chars = res
        self.account.setText(self._account)
        self.settings["account"] = self._account
        preferred = self._league_choice if self._league_choice is not None else self.settings.get("import_league", "")
        while self.league_layout.count():
            button = self.league_layout.takeAt(0).widget()
            if button is not None:
                self.league_group.removeButton(button)
                button.deleteLater()
        groups = league_groups(chars)
        for name, count in [("", len(chars)), *groups]:
            button = QPushButton(f"{name or '전체'} {count}")
            button.setObjectName("FilterChip")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("league", name)
            self.league_group.addButton(button)
            self.league_layout.addWidget(button)
        self.league_layout.addStretch(1)
        self.char_list.clear()
        rows = []
        for char in chars:
            try:
                level = int(char.get("level", 0))
            except (TypeError, ValueError, OverflowError):
                level = 0
            rows.append((char, level))
        rows.sort(key=lambda row: (league_sort_key(league_of(row[0])), -row[1]))
        for c, level in rows:
            it = QListWidgetItem(f"  {c.get('name')}    Lv {level}  ·  {c.get('class')}  ·  {league_of(c)}")
            it.setData(Qt.ItemDataRole.UserRole, c)
            self.char_list.addItem(it)
        selected = preferred if preferred in {name for name, _ in groups} else ""
        self._filter_league(selected)

    def _filter_league(self, league: str, remember: bool = False) -> None:
        for button in self.league_group.buttons():
            button.setChecked(button.property("league") == league)
        current = self.char_list.currentItem()
        visible = []
        for row in range(self.char_list.count()):
            item = self.char_list.item(row)
            item.setHidden(bool(league) and league_of(item.data(Qt.ItemDataRole.UserRole)) != league)
            if not item.isHidden():
                visible.append(item)
        if current is None or current.isHidden():
            if visible:
                self.char_list.setCurrentItem(visible[0])
            else:
                self.char_list.setCurrentRow(-1)
        total = self.char_list.count()
        text = (f"{league} 캐릭터 {len(visible)}개 (전체 {total}개). 가져올 캐릭터를 선택하세요."
                if league else f"캐릭터 {total}개. 가져올 캐릭터를 선택하세요.")
        self._set_status(text)
        if remember:
            self._league_choice = league
            self.settings["import_league"] = league

    def _on_err(self, msg: str) -> None:
        self._set_busy(False)
        self._set_status(msg, True)

    # ---- 가져오기 ----
    def _do_import(self) -> None:
        if self._busy:
            return
        if self.pages.currentIndex() == 0:
            it = self.char_list.currentItem()
            if it is None:
                self._load_list() if not self.char_list.count() else self._set_status("캐릭터를 선택하세요.", True)
                return
            c = it.data(Qt.ItemDataRole.UserRole)
            realm = self.realm.currentData()
            account = self._account or self.account.text().strip()
            self._set_busy(True, f"{c['name']} 데이터 받는 중… (패시브 트리 · 장비 · 스킬)")

            def done(js):
                self.kind, self.payload, self.name = "json", js, c["name"]
                self.source = {"type": "account", "realm": realm, "account": account, "character": c}
                self.accept()

            run_async(lambda: importers.fetch_character(account, realm, c), done, self._on_err)
        else:
            text = self.code.toPlainText()
            self._set_busy(True, "빌드 코드 확인 중…")

            def done(res):
                xml, origin = res
                self.kind, self.payload = "xml", xml
                self.name = self.code_name.text().strip() or ""
                self.source = {"type": "code", "link": origin if origin.startswith("http") else ""}
                self.accept()

            run_async(lambda: importers.resolve_code_or_link(text), done, self._on_err)
