"""사용자가 검색을 눌렀을 때만 브라우저 또는 거래소 API를 실행한다."""
from __future__ import annotations

import math
import time
from uuid import uuid4

from PySide6.QtCore import QEvent, QLocale, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QCursor, QDoubleValidator, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QScrollArea, QSizePolicy, QStyle, QStyleOptionButton,
                               QStylePainter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

import winutil
from asyncjob import run_async
from itemmodel import ItemModel, parse
from theme import build_qss
from trade import browser, config, focus_log, heist
from trade.query import (INFLUENCE_LABELS, SearchTarget, build_query, conditions, item_info, league_for,
                         result_rows, search_target, summary)

TRADE_WINDOW_STYLE = """
QWidget#TradeHero {
    background: #28221d;
    border: 1px solid #58462f;
    border-left: 4px solid #d8a759;
}
QLabel#TradeCaption { color: #f0c682; font-weight: 700; }
QLabel#TradeTarget { color: #f6f0e5; font-size: 28px; font-weight: 700; }
QLabel#TradeScope {
    color: #f3cf95; background: #352a1d; border: 1px solid #6a553b;
    border-radius: 6px; padding: 3px 9px;
}
QLabel#TradeSource { color: #c2c5cb; }
QLabel#TradeResultStatus {
    color: #e3e4e7; background: #191d23; border: 1px solid #343943; padding: 6px;
}
QPushButton:focus, QPushButton#FilterChip:focus { border: 1px solid palette(highlight); }
QCheckBox:focus { outline: 1px solid palette(highlight); }
QPushButton#TradeSearch:enabled {
    color: #17120b; background: #e8bc74; border: 2px solid #e8bc74; font-weight: 700;
}
QPushButton#TradeSearch:hover { background: #f3cf95; }
QPushButton#TradeSearch:focus:enabled { border-color: #ffffff; }
"""


class _ElidedText:
    def paintEvent(self, event) -> None:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(self.text_rect, option, self)
        option.text = self.fontMetrics().elidedText(option.text, Qt.TextElideMode.ElideRight, rect.width())
        painter = QStylePainter(self)
        painter.drawControl(self.control, option)


class _OptionCheck(_ElidedText, QCheckBox):
    text_rect = QStyle.SubElement.SE_CheckBoxContents
    control = QStyle.ControlElement.CE_CheckBox


class _ScopeButton(_ElidedText, QPushButton):
    text_rect = QStyle.SubElement.SE_PushButtonContents
    control = QStyle.ControlElement.CE_PushButton


def _wrapped_label() -> QLabel:
    label = QLabel()
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


class TradeWindow(QWidget):
    def __init__(self, source_fn=lambda: None):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("거래소 시세 검색")
        self.setStyleSheet(build_qss() + TRADE_WINDOW_STYLE)
        self.resize(760, 680)
        self.source_fn = source_fn
        self.model = None
        self._prev_fg = 0
        self._open_id = ""
        self._close_intent = None
        self._busy = False
        self._loading = False
        self._generation = 0
        self._until = 0.0
        self._placing = False
        self._position_timer = QTimer(self, singleShot=True, interval=250, timeout=self._save_position)
        self._result_link = ""
        self.stats = []
        self.inputs = []
        self.influence_inputs = {}
        layout = QVBoxLayout(self)
        self.mode_label = _wrapped_label()
        layout.addWidget(self.mode_label)
        hero = QWidget()
        hero.setObjectName("TradeHero")
        hero.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(14, 10, 14, 10)
        self.target_caption = QLabel("검색 대상")
        self.target_caption.setObjectName("TradeCaption")
        hero_layout.addWidget(self.target_caption)
        self.title = _wrapped_label()
        self.title.setObjectName("TradeTarget")
        hero_layout.addWidget(self.title)
        self.scope_badge = QLabel()
        self.scope_badge.setTextFormat(Qt.TextFormat.PlainText)
        self.scope_badge.setObjectName("TradeScope")
        hero_layout.addWidget(self.scope_badge, alignment=Qt.AlignmentFlag.AlignLeft)
        self.copied_item = _wrapped_label()
        self.copied_item.setObjectName("TradeSource")
        hero_layout.addWidget(self.copied_item)
        layout.addWidget(hero)
        self.focus_hint = QLabel("거래소 창을 클릭하면 입력할 수 있습니다")
        self.focus_hint.hide()
        layout.addWidget(self.focus_hint)
        controls = QWidget()
        controls.setObjectName("TradeControls")
        control_layout = QVBoxLayout(controls)
        control_layout.setContentsMargins(0, 0, 0, 0)
        self.league = QComboBox()
        self.league.setEditable(True)
        self.league.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.league.setAccessibleName("리그")
        self.league.lineEdit().setAccessibleName("리그 이름")
        self.league.lineEdit().setPlaceholderText("리그 이름을 입력하세요")
        league_row = QHBoxLayout()
        league_name = QLabel("리그")
        league_name.setBuddy(self.league)
        league_row.addWidget(league_name)
        league_row.addWidget(self.league, 1)
        control_layout.addLayout(league_row)
        header = QHBoxLayout()
        self.ilvl = QCheckBox("아이템 레벨")
        self.links = QCheckBox("링크")
        self.corrupted = QCheckBox("타락 여부")
        self.base_button = _ScopeButton("정확한 베이스")
        self.base_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.base_button.setObjectName("FilterChip")
        self.base_button.setCheckable(True)
        self.base_button.hide()
        self.base_button.toggled.connect(self._base_changed)
        control_layout.addWidget(self.base_button)
        for widget in (self.ilvl, self.links, self.corrupted):
            header.addWidget(widget)
            widget.toggled.connect(self._conditions_changed)
        header.addStretch(1)
        header.addWidget(QLabel("가판대 매물만"))
        control_layout.addLayout(header)
        layout.addWidget(controls)
        options_header = QHBoxLayout()
        options_title = QLabel("검색 조건")
        options_title.setObjectName("SectionLabel")
        options_header.addWidget(options_title, 1)
        self.select_all = QPushButton("전체 선택")
        self.clear_all = QPushButton("전체 해제")
        for button, state, name in ((self.select_all, True, "검색 옵션 전체 선택"),
                                    (self.clear_all, False, "검색 옵션 전체 해제")):
            button.setAccessibleName(name)
            button.clicked.connect(lambda _checked, state=state: self._set_all_options(state))
            button.hide()
            options_header.addWidget(button)
        layout.addLayout(options_header)
        scroll = QScrollArea()
        scroll.setAccessibleName("검색 옵션")
        scroll.setMinimumHeight(84)
        scroll.setWidgetResizable(True)
        self.stat_box = QWidget()
        self.stat_layout = QVBoxLayout(self.stat_box)
        self.stat_layout.setContentsMargins(6, 6, 6, 6)
        self.stat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.stat_box)
        layout.addWidget(scroll, 1)
        self.hint = QLabel()
        self.hint.setTextFormat(Qt.TextFormat.PlainText)
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        results_title = QLabel("검색 결과")
        results_title.setObjectName("SectionLabel")
        layout.addWidget(results_title)
        self.result_summary = QLabel()
        self.result_summary.setObjectName("TradeResultStatus")
        self.result_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.result_summary.setWordWrap(True)
        layout.addWidget(self.result_summary)
        self.table = QTableWidget(0, 4)
        self.table.setAccessibleName("검색 결과 목록")
        self.table.setHorizontalHeaderLabels(["가격", "판매자", "등록", "아이템 레벨"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.search_button = QPushButton()
        self.search_button.setObjectName("TradeSearch")
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
        self._conditions_changed()

    def _clear_results(self, message: str) -> None:
        self._result_link = ""
        self.open_button.setEnabled(False)
        self.table.setRowCount(0)
        self.result_summary.setText(message)

    def _conditions_changed(self) -> None:
        if self._loading or not hasattr(self, "info"):
            return
        self._generation += 1
        self._update_bulk_buttons()
        self._clear_results("조건이 바뀌었습니다. 검색을 눌러 주세요")
        self._validate()

    def _base_changed(self) -> None:
        self._update_target()
        self._conditions_changed()

    def _update_target(self) -> None:
        target = SearchTarget() if self._error else search_target(self.info, self.base_button.isChecked())
        self.title.setText(target.label)
        self.title.setAccessibleName(f"검색 대상: {target.label}")
        if target.category:
            scope = f"{target.label} 전체"
        elif target.name:
            scope = "고유"
        elif target.base is None:
            scope = ""
        elif self.info.identity and self.info.identity.gem_level is not None:
            scope = "젬"
        else:
            scope = "정확한 베이스"
        self.scope_badge.setText(scope)
        self.scope_badge.setVisible(bool(scope))
        copied = self.model.name if self.model else ""
        distinct = bool(copied and copied not in (target.label, target.name))
        exact = search_target(self.info, True) if scope else SearchTarget()
        source_base = self.model.base if self.model else ""
        generated = (self.info.rarity == "Rare" and source_base and exact.base
                     and source_base not in copied and exact.base not in copied)
        unused = distinct and (generated or (target.category and copied == exact.base))
        suffix = " · 검색에 사용하지 않음" if unused else ""
        self.copied_item.setText(f"복사한 이름: {copied}{suffix}")
        self.copied_item.setVisible(distinct)
        label = f"{target.label} 전체 검색" if target.category else f"정확한 베이스: {target.label}"
        self.base_button.setText(label)
        self.base_button.setAccessibleName(f"검색 범위: {label}")
        self.base_button.setToolTip(label)

    def _enabled_options(self) -> list[QCheckBox]:
        return [check for check, _, _ in self.inputs if check.isEnabled()]

    def _update_bulk_buttons(self) -> None:
        checks = self._enabled_options()
        self.select_all.setVisible(bool(checks))
        self.clear_all.setVisible(bool(checks))
        self.select_all.setEnabled(any(not check.isChecked() for check in checks))
        self.clear_all.setEnabled(any(check.isChecked() for check in checks))

    def _set_all_options(self, checked: bool) -> None:
        changed = [check for check in self._enabled_options() if check.isChecked() != checked]
        for check in changed:
            with QSignalBlocker(check):
                check.setChecked(checked)
        if changed:
            self._conditions_changed()

    def load(self, item: ItemModel | str | None, hwnd: int = 0) -> None:
        self._loading = True
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
        api = self.current_mode == "api"
        mode_name = "게임 위 시세 모드 (공식 문서 밖 API 사용)" if api else "브라우저 모드"
        self.mode_label.setText(f"POE Delta · {mode_name}")
        self.search_button.setText("검색" if api else "브라우저로 검색")
        self.table.setVisible(api and self.info.supported)
        self.open_button.setVisible(api and self.info.supported)
        self._clear_results("검색할 수 없는 아이템입니다" if not self.info.supported or self._error else
                            "검색을 눌러 결과를 확인하세요" if api else "브라우저에서 결과를 확인하세요")
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
        scoped = not self._error and search_target(self.info, True) != search_target(self.info, False)
        self.base_button.setChecked(scoped and not search_target(self.info).category)
        self._update_target()
        self.base_button.setVisible(scoped)
        self.stats = conditions(self.info, trade.get("min_ratio", 0.9)) if self.info.supported or self.info.heist else []
        self.inputs = []
        self.influence_inputs = {}
        while self.stat_layout.count():
            widget = self.stat_layout.takeAt(0).widget()
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        if self.info.heist and self.info.heist.area is not None and not heist.area_enabled(self.info.category):
            area_note = _wrapped_label()
            area_note.setText(f"지역 레벨 {self.info.heist.area} · 지역 레벨 조건은 아직 지원하지 않습니다")
            self.stat_layout.addWidget(area_note)
        if self.info.influences or self.info.eldritch_sources:
            influence_box = QWidget()
            influence_row = QGridLayout(influence_box)
            influence_row.addWidget(QLabel("영향력"), 0, 0, 1, 2)
            for i, name in enumerate(self.info.influences):
                check = QCheckBox(INFLUENCE_LABELS[name])
                check.setChecked(True)
                check.toggled.connect(self._conditions_changed)
                self.influence_inputs[name] = check
                influence_row.addWidget(check, 1 + i // 2, i % 2)
            self.stat_layout.addWidget(influence_box)
            if self.info.eldritch_sources:
                sources = _wrapped_label()
                sources.setText("섬뜩한 영향력: " + " · ".join(self.info.eldritch_sources))
                self.stat_layout.addWidget(sources)
        sections = {}
        for implicit, title in ((True, "고정 옵션"), (False, "일반 및 기타 옵션")):
            if any((condition.kind == "implicit") == implicit for condition in self.stats):
                section = QWidget()
                section.setObjectName("implicitOptions" if implicit else "explicitOptions")
                section_layout = QVBoxLayout(section)
                section_layout.setContentsMargins(6, 6, 6, 6)
                heading = QLabel(title)
                heading.setObjectName("SectionLabel")
                column_headers = QHBoxLayout()
                column_headers.addWidget(heading, 1)
                for text in ("최소", "최대"):
                    label = QLabel(text)
                    label.setFixedWidth(52)
                    column_headers.addWidget(label)
                section_layout.addLayout(column_headers)
                self.stat_layout.addWidget(section)
                sections[implicit] = section_layout
        for condition in self.stats:
            row = QWidget()
            form = QHBoxLayout(row)
            form.setContentsMargins(0, 3, 0, 3)
            check = _OptionCheck(condition.text)
            check.setChecked(condition.checked)
            check.setEnabled(bool(condition.match.id))
            check.setToolTip("\n".join(part for part in (condition.text, condition.match.reason) if part))
            check.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            check.setMinimumWidth(64)
            badge = QLabel("일반" if condition.badge == "explicit" else condition.badge)
            minimum, maximum = QLineEdit(), QLineEdit()
            for box, value, placeholder in ((minimum, condition.minimum, "최소"), (maximum, condition.maximum, "최대")):
                if condition.kind != "gem_filter":
                    validator = QDoubleValidator(box)
                    validator.setLocale(QLocale.c())
                    box.setValidator(validator)
                box.setPlaceholderText(placeholder)
                box.setFixedWidth(52)
                box.setAccessibleName(f"{condition.text} {placeholder}")
                box.setText("" if value is None else f"{value:g}")
                box.setEnabled(bool(condition.match.id))
                if condition.kind in ("heist_option", "heist_not") or (condition.kind == "heist_job" and box is maximum):
                    box.hide()
                box.textChanged.connect(self._conditions_changed)
            if not condition.match.id:
                row.setStyleSheet("QLabel, QCheckBox { color: #777777; }")
                row.setToolTip(condition.match.reason)
            form.addWidget(check, 1)
            form.addWidget(badge)
            if condition.kind in ("explicit", "fractured"):
                switch = QPushButton("종류 전환")
                switch.setAccessibleName(f"{condition.text} 종류 전환")
                switch.setEnabled(bool(condition.match.alternate_id))
                if not condition.match.alternate_id:
                    switch.setToolTip("같은 옵션에 대응하는 일반·분열 ID가 모두 있어야 합니다")
                switch.clicked.connect(lambda _, c=condition, b=badge: self._switch_kind(c, b))
                form.addWidget(switch)
            form.addWidget(minimum)
            form.addWidget(maximum)
            check.toggled.connect(self._conditions_changed)
            sections[condition.kind == "implicit"].addWidget(row)
            self.inputs.append((check, minimum, maximum))
        if not self.inputs:
            self.stat_layout.addWidget(QLabel("표시할 검색 옵션이 없습니다"))
        elif not self._enabled_options():
            self.stat_layout.addWidget(QLabel("선택할 수 있는 검색 옵션이 없습니다"))
        self._update_bulk_buttons()
        self.search_button.setVisible(bool(self.info.supported or self.info.heist))
        self._loading = False
        self._validate()

    def _switch_kind(self, condition, badge) -> None:
        condition.switch_kind()
        badge.setText("일반" if condition.badge == "explicit" else condition.badge)
        self._conditions_changed()

    def _query(self) -> dict:
        for condition, (check, minimum, maximum) in zip(self.stats, self.inputs):
            condition.checked = check.isChecked()
            if condition.kind == "gem_filter":
                if condition.checked:
                    try:
                        condition.minimum, condition.maximum = (
                            int(text) if text else None for text in (minimum.text().strip(), maximum.text().strip())
                        )
                    except ValueError:
                        raise ValueError(f"{condition.text}: 정수를 입력하세요") from None
                continue
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
            self.result_summary.setText("브라우저에서 결과를 확인하세요")
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
