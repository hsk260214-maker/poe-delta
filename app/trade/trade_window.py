"""사용자가 검색을 눌렀을 때만 브라우저 또는 거래소 API를 실행한다."""
from __future__ import annotations

import math
import time
from uuid import uuid4

from PySide6.QtCore import QEvent, QLocale, Qt, QTimer
from PySide6.QtGui import QCursor, QDoubleValidator, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QScrollArea, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

import winutil
from asyncjob import run_async
from itemmodel import ItemModel, parse
from theme import build_qss
from trade import browser, config, focus_log
from trade.query import INFLUENCE_LABELS, build_query, conditions, item_info, league_for, result_rows, summary


class TradeWindow(QWidget):
    def __init__(self, source_fn=lambda: None):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("거래소 시세 검색")
        self.setStyleSheet(build_qss())
        self.resize(760, 680)
        self.source_fn = source_fn
        self.model = None
        self._prev_fg = 0
        self._open_id = ""
        self._close_intent = None
        self._busy = False
        self._generation = 0
        self._until = 0.0
        self._placing = False
        self._position_timer = QTimer(self, singleShot=True, interval=250, timeout=self._save_position)
        self._result_link = ""
        self.stats = []
        self.inputs = []
        self.influence_inputs = {}
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.title)
        self.focus_hint = QLabel("거래소 창을 클릭하면 입력할 수 있습니다")
        self.focus_hint.hide()
        layout.addWidget(self.focus_hint)
        self.mode_label = QLabel()
        layout.addWidget(self.mode_label)
        self.league = QComboBox()
        self.league.setEditable(True)
        self.league.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.league.lineEdit().setPlaceholderText("리그 이름을 입력하세요 (예: 현재 챌린지 리그 이름)")
        layout.addWidget(self.league)
        header = QHBoxLayout()
        self.ilvl = QCheckBox("아이템 레벨")
        self.links = QCheckBox("링크")
        self.corrupted = QCheckBox("타락 여부")
        self.base_button = QPushButton("정확한 베이스")
        self.base_button.setCheckable(True)
        self.base_button.hide()
        self.base_button.toggled.connect(self._validate)
        header.addWidget(self.base_button)
        for widget in (self.ilvl, self.links, self.corrupted):
            header.addWidget(widget)
            widget.toggled.connect(self._validate)
        header.addStretch(1)
        header.addWidget(QLabel("가판대 매물만"))
        layout.addLayout(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.stat_box = QWidget()
        self.stat_layout = QVBoxLayout(self.stat_box)
        self.stat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.stat_box)
        layout.addWidget(scroll, 1)
        self.hint = QLabel()
        self.hint.setTextFormat(Qt.TextFormat.PlainText)
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.result_summary = QLabel()
        self.result_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.result_summary.setWordWrap(True)
        layout.addWidget(self.result_summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["가격", "판매자", "등록", "아이템 레벨"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.search_button = QPushButton()
        self.search_button.clicked.connect(self.search)
        self.open_button = QPushButton("거래소에서 열기")
        self.open_button.clicked.connect(lambda: self._result_link and browser.open_url(self._result_link))
        close = QPushButton("닫기")
        close.clicked.connect(lambda: self._request_close("button"))
        for widget in (self.search_button, self.open_button, close):
            footer.addWidget(widget)
        layout.addLayout(footer)
        QShortcut(QKeySequence("Esc"), self, activated=self._close_on_escape)
        QShortcut(QKeySequence("Return"), self, activated=self.search)
        QShortcut(QKeySequence("Enter"), self, activated=self.search)
        self.league.currentTextChanged.connect(self._league_changed)
        self.timer = QTimer(self, interval=200, timeout=self._validate)
        self.timer.start()

    def _league_changed(self) -> None:
        config.save(league=self.league.currentText().strip())
        self._validate()

    def load(self, item: ItemModel | str | None, hwnd: int = 0) -> None:
        self._generation += 1
        self.model = parse(item) if isinstance(item, str) else item
        self._prev_fg = hwnd
        trade = config.settings()
        self.server = trade.get("server", config.default_server())
        self.current_mode = config.mode()
        self._error = ""
        try:
            self.info = item_info(self.model, self.server)
        except ValueError as error:
            self.info = item_info(self.model, config.OFFICIAL)
            self._error = str(error)
        self.title.setText(self.model.name if self.model else "지원하지 않는 아이템")
        api = self.current_mode == "api"
        self.mode_label.setText("게임 위 시세 모드 (공식 문서 밖 API 사용)" if api else "브라우저 모드")
        self.search_button.setText("검색" if api else "브라우저로 검색")
        self.table.setVisible(api and self.info.supported)
        self.open_button.setVisible(api and self.info.supported)
        self.open_button.setEnabled(False)
        self._result_link = ""
        self.table.setRowCount(0)
        self.result_summary.setText("" if api else "브라우저에서 결과를 확인하세요")
        self.league.blockSignals(True)
        self.league.clear()
        self.league.setEditText(league_for(self.source_fn(), trade.get("league", "")))
        self.league.blockSignals(False)
        self.ilvl.setChecked(False)
        self.ilvl.setVisible(self.info.rarity == "Rare" and self.info.identity is None)
        self.ilvl.setText(f"아이템 레벨 ≥ {self.info.ilvl}")
        self.links.setChecked(self.info.links >= 5)
        self.links.setVisible(self.info.links >= 5)
        self.links.setText(f"링크 ≥ {self.info.links}")
        self.corrupted.setChecked(True)
        self.corrupted.setText("타락" if self.info.corrupted else "타락 아님")
        self.base_button.setChecked(False)
        self.base_button.setVisible(bool(self.info.supported and self.info.equipment_category))
        self.stats = conditions(self.info, trade.get("min_ratio", 0.9)) if self.info.supported else []
        self.inputs = []
        self.influence_inputs = {}
        while self.stat_layout.count():
            widget = self.stat_layout.takeAt(0).widget()
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        if self.info.influences or self.info.eldritch_sources:
            influence_box = QWidget()
            influence_row = QHBoxLayout(influence_box)
            influence_row.addWidget(QLabel("영향력"))
            for name in self.info.influences:
                check = QCheckBox(INFLUENCE_LABELS[name])
                check.setChecked(True)
                check.toggled.connect(self._validate)
                self.influence_inputs[name] = check
                influence_row.addWidget(check)
            influence_row.addStretch(1)
            self.stat_layout.addWidget(influence_box)
            if self.info.eldritch_sources:
                self.stat_layout.addWidget(QLabel("섬뜩한 영향력: " + " · ".join(self.info.eldritch_sources)))
        sections = {}
        for implicit, title in ((True, "고정 옵션"), (False, "일반 및 기타 옵션")):
            if any((condition.kind == "implicit") == implicit for condition in self.stats):
                section = QWidget()
                section.setObjectName("implicitOptions" if implicit else "explicitOptions")
                section_layout = QVBoxLayout(section)
                heading = QLabel(title)
                heading.setObjectName("SectionLabel")
                section_layout.addWidget(heading)
                self.stat_layout.addWidget(section)
                sections[implicit] = section_layout
        for condition in self.stats:
            row = QWidget()
            form = QHBoxLayout(row)
            check = QCheckBox(condition.text)
            check.setChecked(condition.checked)
            check.setEnabled(bool(condition.match.id))
            check.setToolTip(condition.match.reason)
            check.setMinimumWidth(350)
            badge = QLabel(condition.badge)
            minimum, maximum = QLineEdit(), QLineEdit()
            for box, value, placeholder in ((minimum, condition.minimum, "최소"), (maximum, condition.maximum, "최대")):
                validator = QDoubleValidator(box)
                validator.setLocale(QLocale.c())
                box.setValidator(validator)
                box.setPlaceholderText(placeholder)
                box.setMaximumWidth(85)
                box.setText("" if value is None else f"{value:g}")
                box.setEnabled(bool(condition.match.id))
                box.textChanged.connect(self._validate)
            if not condition.match.id:
                row.setStyleSheet("QLabel, QCheckBox { color: #777777; }")
                row.setToolTip(condition.match.reason)
            form.addWidget(check, 1)
            form.addWidget(badge)
            if condition.kind in ("explicit", "fractured"):
                switch = QPushButton("종류 전환")
                switch.setEnabled(bool(condition.match.alternate_id))
                if not condition.match.alternate_id:
                    switch.setToolTip("같은 옵션에 대응하는 일반·분열 ID가 모두 있어야 합니다")
                switch.clicked.connect(lambda _, c=condition, b=badge: self._switch_kind(c, b))
                form.addWidget(switch)
            form.addWidget(minimum)
            form.addWidget(maximum)
            check.toggled.connect(self._validate)
            sections[condition.kind == "implicit"].addWidget(row)
            self.inputs.append((check, minimum, maximum))
        self.search_button.setVisible(self.info.supported)
        self._validate()

    def _switch_kind(self, condition, badge) -> None:
        condition.switch_kind()
        badge.setText(condition.badge)
        self._validate()

    def _query(self) -> dict:
        for condition, (check, minimum, maximum) in zip(self.stats, self.inputs):
            condition.checked = check.isChecked()
            for name, box in (("minimum", minimum), ("maximum", maximum)):
                text = box.text().strip()
                if text and not box.hasAcceptableInput():
                    raise ValueError("최소·최대값을 숫자로 입력하세요")
                value = float(text) if text else None
                setattr(condition, name, int(value) if value is not None and value.is_integer() else value)
            if condition.minimum is not None and condition.maximum is not None and condition.minimum > condition.maximum:
                raise ValueError("최소값은 최대값보다 클 수 없습니다")
        return build_query(self.info, self.stats, ilvl=self.ilvl.isChecked(),
                           links=self.links.isChecked(), corrupted=self.corrupted.isChecked(),
                           exact_base=self.base_button.isChecked(),
                           influences={name for name, check in self.influence_inputs.items() if check.isChecked()})

    def _validate(self) -> None:
        if not hasattr(self, "info"):
            return
        error = self._error
        if not self.info.supported:
            error = self.info.message
        elif self._busy:
            error = "검색 중입니다"
        elif self._until > time.monotonic():
            error = f"요청 제한: {math.ceil(self._until - time.monotonic())}초 뒤 다시 검색할 수 있습니다"
        elif not error:
            try:
                query = self._query()
                if self.current_mode == "browser":
                    browser.build_url(self.league.currentText(), query, self.server, self.model.lang)
            except ValueError as problem:
                error = str(problem)
        self.hint.setText(error)
        self.search_button.setEnabled(not error)

    def search(self) -> None:
        self._validate()
        if not self.search_button.isEnabled() or not self.info.supported:
            return
        if config.mode() != self.current_mode:
            self.load(self.model, self._prev_fg)
            return
        query = self._query()
        league, server, lang = self.league.currentText().strip(), self.server, self.model.lang
        if self.current_mode == "browser":
            browser.open_url(browser.build_url(league, query, server, lang))
            return
        from trade.api import TradeClient, TradeError

        client = TradeClient()
        generation = self._generation
        self._busy = True
        self.open_button.setEnabled(False)
        self._validate()

        def work():
            try:
                leagues = client.leagues(server, lang)
                chosen = league if league in leagues else leagues[0]
                response = client.search(chosen, query, server, lang)
                ids = response.get("result", [])[:20]
                fetched = []
                for start in range(0, len(ids), 10):
                    fetched.extend(client.fetch(ids[start:start + 10], response["id"], server, lang).get("result", []))
                return {"league": chosen, "leagues": leagues, "id": response["id"],
                        "total": response.get("total", 0), "rows": result_rows({"result": fetched}),
                        "wait": client.remaining(server)}
            except TradeError as error:
                return {"error": str(error), "wait": error.retry_after}

        def complete(result):
            self._busy = False
            self._until = time.monotonic() + result.get("wait", 0)
            if generation == self._generation:
                if "error" in result:
                    self.result_summary.setText(result["error"])
                else:
                    self.league.blockSignals(True)
                    self.league.clear()
                    self.league.addItems(result["leagues"])
                    self.league.setCurrentText(result["league"])
                    self.league.blockSignals(False)
                    config.save(league=result["league"])
                    self._result_link = browser.result_url(result["league"], result["id"], server, lang)
                    self.open_button.setEnabled(True)
                    prefix = f"리그를 {result['league']}(으)로 바꿨습니다 · " if result["league"] != league else ""
                    self.result_summary.setText(prefix + summary(result["total"], result["rows"]))
                    self.table.setRowCount(len(result["rows"]))
                    for i, row in enumerate(result["rows"]):
                        values = [f"{row['amount']:g} {row['currency']}" if row["amount"] is not None else "가격 없음",
                                  row["seller"], row["age"], str(row["ilvl"])]
                        for j, value in enumerate(values):
                            self.table.setItem(i, j, QTableWidgetItem(value))
            self._validate()

        def failed(_message):
            complete({"error": "거래소 검색을 완료하지 못했습니다. 다시 검색하세요"})

        self._job = run_async(work, complete, failed)

    def show_item(self, item, hwnd: int = 0) -> None:
        self._open_id = uuid4().hex
        self._close_intent = None
        self.focus_hint.hide()
        if self._position_timer.isActive():
            self._save_position()
        self.load(item, hwnd)
        self._placing = True
        position = config.settings().get("window") or {}
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        if position:
            from PySide6.QtCore import QPoint
            screen = QGuiApplication.screenAt(QPoint(position["x"], position["y"])) or screen
        available = screen.availableGeometry()
        self.resize(min(self.width(), available.width()), min(self.height(), available.height()))
        x, y = position.get("x", cursor.x() - self.width() // 2), position.get("y", cursor.y() - 40)
        self.move(max(available.left(), min(x, available.right() - self.width() + 1)),
                  max(available.top(), min(y, available.bottom() - self.height() + 1)))
        self.show()
        self._placing = False
        own = int(self.winId())
        activated = winutil.focus_window(own, allow_alt_fallback=False)
        foreground = winutil.foreground_window()
        success = activated and foreground == own
        if success:
            self.league.setFocus()
        else:
            self.focus_hint.show()
        focus_log.record(self._open_id, "open", winutil.foreground_category(foreground),
                         activation="success" if success else "denied")

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.focus_hint.hide()

    def _close_on_escape(self) -> None:
        if self.isActiveWindow():
            self._request_close("esc")

    def _request_close(self, source: str) -> None:
        self._close_intent = source
        try:
            self.close()
        finally:
            self._close_intent = None

    def moveEvent(self, event) -> None:
        if self.isVisible() and not self._placing and event.spontaneous():
            self._position_timer.start()
        super().moveEvent(event)

    def _save_position(self) -> None:
        self._position_timer.stop()
        config.save(window={"x": self.x(), "y": self.y()})

    def closeEvent(self, event) -> None:
        try:
            foreground = winutil.foreground_window()
            was_foreground = self.isVisible() and foreground == int(self.winId())
            source = self._close_intent or ("system" if event.spontaneous() else "code")
            open_id, game = self._open_id, self._prev_fg
            if open_id:
                focus_log.record(open_id, "close", winutil.foreground_category(foreground),
                                 source=source, was_foreground=was_foreground)
            if self._position_timer.isActive():
                self._save_position()
            super().closeEvent(event)
            if open_id and event.isAccepted() and was_foreground and source != "code":
                QTimer.singleShot(0, self, lambda: self._restore_after_close(open_id, game))
        finally:
            self._close_intent = None

    def _restore_after_close(self, open_id: str, game: int) -> None:
        if self._open_id != open_id or self.isVisible():
            return
        foreground = winutil.foreground_window()
        category = winutil.foreground_category(foreground)
        if game and foreground == game:
            result = "game_already_foreground"
        elif not winutil.window_exists(game):
            result = "invalid_game"
        elif category != "poe_delta":
            result = "unrelated_foreground"
        else:
            result = ("restored" if winutil.focus_window(game, allow_alt_fallback=False)
                      and winutil.foreground_window() == game else "denied")
        focus_log.record(open_id, "after_hide", category, result=result)
