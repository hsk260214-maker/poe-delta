"""지도 옵션 프리셋과 보관함 정규식."""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QMimeData, QSignalBlocker, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

import mapcheck
import map_presets
import map_regex
from storage import load_settings, save_settings

T17 = "#d77fe0"
MAVEN_ALL_BOSSES = map_presets.MAVEN_ALL_BOSSES


class RegexOutput(QLineEdit):
    def __init__(self, copy_result):
        super().__init__()
        self.copy_result = copy_result
        self.setReadOnly(True)
        self.setAccessibleName("보관함 정규식 결과")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_result()
            event.accept()
            return
        super().keyPressEvent(event)


class MapAvoidCard:
    def __init__(self, page, v):
        self.page = page
        settings = load_settings()
        self.catalog = mapcheck.catalog()
        self.regex_patterns = map_regex.load_patterns(self.catalog)
        self.data_issue = (map_regex.CATALOG_UNAVAILABLE if not self.catalog else
                           map_regex.FRAGMENTS_UNAVAILABLE if not self.regex_patterns else "")
        info = QLabel("선호·비선호를 다시 누르면 해제돼요. 지도에서 Ctrl+C를 누르면 비선호 옵션만 알려 드려요.")
        info.setObjectName("SectionLabel")
        info.setWordWrap(True)
        v.addWidget(info)

        self._preset_controls(v)
        regex_title = QLabel("보관함 정규식")
        regex_title.setObjectName("SectionLabel")
        header = QHBoxLayout()
        header.addWidget(regex_title, 1)
        self.regex_language = QComboBox()
        self.regex_language.setAccessibleName("정규식 출력 언어")
        self.regex_language.addItem("한글 정규식", "ko")
        self.regex_language.addItem("English 정규식", "en")
        self.regex_language.setCurrentIndex(max(0, self.regex_language.findData(settings.get("map_regex_language"))))
        header.addWidget(self.regex_language)
        v.addLayout(header)
        self._limit_controls(v)
        guide = QLabel("수치 조건은 지도 속성 값이 999% 이하라고 가정해요. 실제 게임 보관함 호환은 아직 확인하지 않았어요.")
        guide.setWordWrap(True)
        v.addWidget(guide)
        output = QHBoxLayout()
        self.regex_text = RegexOutput(self._copy_regex)
        output.addWidget(self.regex_text, 1)
        self.regex_count = QLabel()
        output.addWidget(self.regex_count)
        self.regex_copy = QPushButton("정규식 복사")
        self.regex_copy.clicked.connect(self._copy_regex)
        output.addWidget(self.regex_copy)
        v.addLayout(output)
        self.regex_status = QLabel()
        self.regex_status.setWordWrap(True)
        v.addWidget(self.regex_status)

        if self.data_issue:
            self.regex_language.setEnabled(False)
            for widget in (self.want_mode, self.limit_mode, *self.limit_inputs.values()):
                widget.setEnabled(False)
            self._update_regex()
            return

        keys = {entry["key"] for entry in self.catalog} - {MAVEN_ALL_BOSSES}
        self.presets, self.active = map_presets.recover(settings, keys)
        stored = map_presets.records(self.presets, self.active)
        if any(settings.get(k) != value for k, value in stored.items()):
            save_settings({**settings, **stored})

        fr = QHBoxLayout()
        fr.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("옵션 검색 (예: 회복, 반사, 저항)")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(280)
        self.search.setMaximumWidth(340)
        self.search.textChanged.connect(lambda _t: self._layout())
        fr.addWidget(self.search)
        self.which = QComboBox()
        for label, key in (("전체", ""), ("일반 지도에 나오는 것", "map"), ("17티어에만 나오는 것", "t17only")):
            self.which.addItem(label, key)
        self.which.currentIndexChanged.connect(lambda _i: self._layout())
        fr.addWidget(self.which)
        self.only = QCheckBox("고른 것만")
        self.only.toggled.connect(lambda _on: self._layout())
        fr.addWidget(self.only)
        fr.addStretch(1)
        self.count = QLabel()
        self.count.setObjectName("DefLine")
        fr.addWidget(self.count)
        clear = QPushButton("이 프리셋 전부 해제")
        clear.clicked.connect(self._clear)
        fr.addWidget(clear)
        v.addLayout(fr)

        host = QWidget()
        self.grid = QGridLayout(host)
        self.grid.setContentsMargins(0, 4, 0, 0)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(4)
        v.addWidget(host)
        self.empty = QLabel()
        self.empty.setObjectName("DefLine")
        v.addWidget(self.empty)

        self.boxes = []
        for e in self.catalog:
            only17 = e["tiers"] == ["t17"]
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(e["ko"] + ("   ◆17티어" if only17 else ""))
            label.setWordWrap(True)
            if only17:
                label.setStyleSheet(f"color: {T17}")
            where = " · ".join(mapcheck.TIER_KO[t] for t in e["tiers"])
            label.setToolTip(f"{e['en']}\n나오는 곳: {where}")
            layout.addWidget(label, 1)
            if e["key"] == MAVEN_ALL_BOSSES:
                label.setText(f"{e['ko']} (정규식 미지원)")
            buttons = []
            for mode, text in (("want", "선호"), ("avoid", "비선호")):
                button = QPushButton(text)
                button.setObjectName("FilterChip")
                button.setCheckable(True)
                button.setEnabled(e["key"] != MAVEN_ALL_BOSSES)
                button.setAccessibleName(f"{e['ko']} {text}")
                button.clicked.connect(lambda _on, k=e["key"], choice=mode: self._pick(k, choice))
                buttons.append(button)
                layout.addWidget(button)
            self.boxes.append((e, row, *buttons))
        self.regex_language.currentIndexChanged.connect(self._language_changed)
        self._refresh()

    @property
    def preset(self):
        return next(row for row in self.presets if row["id"] == self.active)

    def _preset_controls(self, parent):
        row = QHBoxLayout()
        row.addWidget(QLabel("프리셋"))
        self.preset_picker = QComboBox()
        self.preset_picker.setAccessibleName("지도 프리셋 선택")
        self.preset_picker.setEnabled(not self.data_issue)
        if not self.data_issue:
            self.preset_picker.currentIndexChanged.connect(self._activate)
        row.addWidget(self.preset_picker)
        self.preset_name = QLineEdit()
        self.preset_name.setAccessibleName("지도 프리셋 이름")
        self.preset_name.setEnabled(not self.data_issue)
        if not self.data_issue:
            self.preset_name.editingFinished.connect(self._rename)
        row.addWidget(self.preset_name, 1)
        for text, action in (("새 프리셋", self._new), ("복제", self._duplicate), ("삭제", self._delete)):
            button = QPushButton(text)
            button.setEnabled(not self.data_issue)
            button.clicked.connect(action)
            row.addWidget(button)
            if text == "삭제":
                self.delete_button = button
        parent.addLayout(row)
        self.preset_status = QLabel()
        self.preset_status.setWordWrap(True)
        parent.addWidget(self.preset_status)

    def _limit_controls(self, parent):
        grid = QGridLayout()
        self.want_mode = QComboBox()
        self.want_mode.setAccessibleName("선호 조건")
        self.want_mode.addItem("선호: 하나라도 있으면", "any")
        self.want_mode.addItem("선호: 모두 있어야", "all")
        if not self.data_issue:
            self.want_mode.currentIndexChanged.connect(lambda _: self._change("mode", self.want_mode.currentData()))
        grid.addWidget(self.want_mode, 0, 0, 1, 2)
        self.limit_mode = QComboBox()
        self.limit_mode.setAccessibleName("화폐·지도 수치 조건")
        self.limit_mode.addItem("화폐·지도: 하나라도", "or")
        self.limit_mode.addItem("화폐·지도: 모두", "and")
        if not self.data_issue:
            self.limit_mode.currentIndexChanged.connect(lambda _: self._change("limit_mode", self.limit_mode.currentData()))
        grid.addWidget(self.limit_mode, 0, 2, 1, 2)
        self.limit_inputs = {}
        for i, (key, name) in enumerate(map_regex.LIMIT_NAMES.items()):
            box = QLineEdit()
            box.setAccessibleName(f"{name} 최소값")
            box.setPlaceholderText("10~999")
            box.setMaximumWidth(90)
            if not self.data_issue:
                box.textChanged.connect(lambda value, k=key: self._set_limit(k, value))
            self.limit_inputs[key] = box
            r, c = divmod(i, 2)
            grid.addWidget(QLabel(f"{name} ≥"), r + 1, c * 2)
            grid.addWidget(box, r + 1, c * 2 + 1)
        parent.addLayout(grid)

    def _save(self, **extra):
        settings = load_settings()
        save_settings({**settings, **map_presets.records(self.presets, self.active), **extra})

    def _refresh(self):
        self.preset_status.clear()
        with QSignalBlocker(self.preset_picker):
            self.preset_picker.clear()
            for row in self.presets:
                self.preset_picker.addItem(row["name"], row["id"])
            self.preset_picker.setCurrentIndex(self.preset_picker.findData(self.active))
        self.preset_name.setText(self.preset["name"])
        self.delete_button.setEnabled(len(self.presets) > 1)
        for field, combo in (("mode", self.want_mode), ("limit_mode", self.limit_mode)):
            with QSignalBlocker(combo):
                combo.setCurrentIndex(combo.findData(self.preset[field]))
        for key, box in self.limit_inputs.items():
            with QSignalBlocker(box):
                box.setText(self.preset["limits"][key])
        selected = dict(self.preset["order"])
        for e, _, want, avoid in self.boxes:
            want.setChecked(selected.get(e["key"]) == "want")
            avoid.setChecked(selected.get(e["key"]) == "avoid")
        self._layout()
        self._update_regex()

    def _activate(self, _index):
        if active := self.preset_picker.currentData():
            if active != self.active:
                self.active = active
                self._save()
                self._refresh()

    def _rename(self):
        name = self.preset_name.text().strip()
        if not 1 <= len(name) <= 20 or any(row["id"] != self.active and row["name"].casefold() == name.casefold()
                                            for row in self.presets):
            self.preset_name.setText(self.preset["name"])
            self.preset_status.setText("이름은 1~20자이며 다른 프리셋과 겹칠 수 없어요.")
        elif name != self.preset["name"]:
            self.preset["name"] = name
            self._save()
            self._refresh()
        else:
            self.preset_name.setText(name)
            self.preset_status.clear()

    def _add(self, row):
        self.presets.append(row)
        self.active = row["id"]
        self._save()
        self._refresh()

    def _new(self):
        self._add(map_presets.blank(map_presets.unique_name("새 프리셋", (row["name"] for row in self.presets))))

    def _duplicate(self):
        name = map_presets.unique_name(self.preset["name"], (row["name"] for row in self.presets), " 복사본")
        duplicate = map_presets.blank(name)
        for key in ("order", "mode", "limits", "limit_mode"):
            duplicate[key] = deepcopy(self.preset[key])
        self._add(duplicate)

    def _delete(self):
        if len(self.presets) > 1:
            index = self.presets.index(self.preset)
            self.presets.pop(index)
            self.active = self.presets[max(0, index - 1)]["id"]
            self._save()
            self._refresh()

    def _change(self, key, value):
        self.preset[key] = value
        self._save()
        self._update_regex()

    def _set_limit(self, key, value):
        self.preset["limits"][key] = value
        self._save()
        self._update_regex()

    def _language_changed(self, _index):
        save_settings({**load_settings(), "map_regex_language": self.regex_language.currentData()})
        self._update_regex()

    def _regex_result(self) -> map_regex.Result:
        if self.data_issue:
            return map_regex.Result(issue=self.data_issue + " 저장된 프리셋과 비선호 목록은 그대로예요.")
        preset = self.preset
        return map_regex.build(map_presets.avoids(preset), self.catalog, self.regex_patterns,
                               self.regex_language.currentData(),
                               wanted=[key for key, mode in preset["order"] if mode == "want"], mode=preset["mode"],
                               limits=preset["limits"], limit_mode=preset["limit_mode"])

    def _update_regex(self) -> None:
        result = self._regex_result()
        self.regex_text.setText(result.text)
        self.regex_text.setEnabled(bool(result.text))
        self.regex_copy.setEnabled(bool(result.text))
        self.regex_count.setText(f"{result.length} / {map_regex.LIMIT}자")
        self.regex_status.setText(result.issue or "복사해서 게임 보관함 검색칸에 직접 붙여 넣으세요.")

    def _copy_regex(self) -> None:
        result = self._regex_result()
        if result.text:
            data = QMimeData()
            data.setText(result.text)
            data.setData(map_regex.CLIPBOARD_MIME, b"1")
            QApplication.clipboard().setMimeData(data)
            self.regex_status.setText("정규식을 복사했어요.")

    def _layout(self) -> None:
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().hide()
        q = self.search.text().strip().lower()
        which = self.which.currentData()
        shown = []
        for e, row, want, avoid in self.boxes:
            if q and q not in e["ko"].lower() and q not in e["en"].lower():
                continue
            if which == "map" and "map" not in e["tiers"]:
                continue
            if which == "t17only" and e["tiers"] != ["t17"]:
                continue
            if self.only.isChecked() and not (want.isChecked() or avoid.isChecked()):
                continue
            shown.append(row)
        half = (len(shown) + 1) // 2
        for i, cb in enumerate(shown):
            self.grid.addWidget(cb, i % half if half else 0, i // half if half else 0)
            cb.show()
        self.empty.setText("" if shown else "조건에 맞는 옵션이 없어요.")
        self.empty.setVisible(not shown)
        self.count.setText(f"{len(self.preset['order'])}개 고름")

    def _pick(self, key, mode):
        previous = dict(self.preset["order"]).get(key)
        order = [pair for pair in self.preset["order"] if pair[0] != key]
        if previous != mode:
            order.append([key, mode])
        self.preset["order"] = order
        self._save()
        self._refresh()

    def _clear(self) -> None:
        if self.preset["order"] or any(self.preset["limits"].values()):
            self.preset["order"] = []
            self.preset["limits"] = dict.fromkeys(map_regex.LIMIT_NAMES, "")
            self._save()
            self._refresh()
