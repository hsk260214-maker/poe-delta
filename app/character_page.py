"""캐릭터 섹션: 등록된 캐릭터(탭)의 PoB 계산 결과, 스킬 선택, 장비 교체 비교."""
from __future__ import annotations

import base64
import html
import zlib

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QDoubleValidator, QIntValidator, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QLineEdit,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from asyncjob import run_async
from characters import CharacterStore
from dialogs import confirm, info
from import_dialog import ImportDialog
from pob import config_ko, importers, installer
from storage import load_settings, save_settings
from titlebar import TabStrip

POS = "#7fc46a"
NEG = "#e0644c"
DIM = "#968b7a"


def fmt_big(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 1e299:
        return "∞"
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:.2f}B"
    if a >= 1e6:
        return f"{v / 1e6:.2f}M"
    if a >= 1e4:
        return f"{v / 1e3:.1f}K"
    if a >= 100:
        return f"{v:,.0f}"
    return f"{v:.1f}".rstrip("0").rstrip(".")


# (key, label, kind) kind: big=큰 수, pct=퍼센트 수치, num=일반
DELTA_STATS = [
    ("FullDPS", "Full DPS", "big"),
    ("CombinedDPS", "Combined DPS", "big"),
    ("TotalEHP", "EHP", "big"),
    ("Life", "생명력", "num"),
    ("EnergyShield", "에너지 보호막", "num"),
    ("Mana", "마나", "num"),
    ("Ward", "수호", "num"),
    ("FireResist", "화염 저항", "pct"),
    ("ColdResist", "냉기 저항", "pct"),
    ("LightningResist", "번개 저항", "pct"),
    ("ChaosResist", "카오스 저항", "pct"),
    ("Armour", "방어도", "num"),
    ("Evasion", "회피", "num"),
    ("EffectiveSpellSuppressionChance", "주문 피해 억제", "pct"),
    ("EffectiveBlockChance", "공격 막기", "pct"),
    ("EffectiveSpellBlockChance", "주문 막기", "pct"),
    ("PhysicalMaximumHitTaken", "물리 최대 피격", "big"),
    ("FireMaximumHitTaken", "화염 최대 피격", "big"),
    ("ColdMaximumHitTaken", "냉기 최대 피격", "big"),
    ("LightningMaximumHitTaken", "번개 최대 피격", "big"),
    ("ChaosMaximumHitTaken", "카오스 최대 피격", "big"),
    ("Str", "힘", "num"),
    ("Dex", "민첩", "num"),
    ("Int", "지능", "num"),
]
ALWAYS = {"FullDPS", "CombinedDPS", "TotalEHP"}
DELTA_STATS.insert(2, ("TotalDPS", "Hit DPS", "big"))


def _items(sec: dict) -> list:
    it = sec.get("items")
    return it if isinstance(it, list) else []


def fmt_plain(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("HeaderCard")
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 14, 16, 14)
    v.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setObjectName("CardTitle")
        v.addWidget(t)
    return f, v


class StatTile(QFrame):
    def __init__(self, title: str, accent: str = ""):
        super().__init__()
        self.setObjectName("StatTile")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 7, 12, 7)
        v.setSpacing(1)
        self.t = QLabel(title)
        self.t.setObjectName("TileTitle")
        self.v = QLabel("—")
        self.v.setObjectName("TileValue")
        if accent:
            self.v.setStyleSheet(f"color: {accent};")
        self.s = QLabel("")
        self.s.setObjectName("TileSub")
        # 긴 부제(스킬 이름 등)가 칸 너비를 늘려 창이 넘치지 않게
        for lab in (self.t, self.s):
            lab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(90)
        v.addWidget(self.t)
        v.addWidget(self.v)
        v.addWidget(self.s)

    def set(self, value: str, sub: str = "") -> None:
        self.v.setText(value)
        self.s.setText(sub)
        self.s.setToolTip(sub)


class CharacterPage(QWidget):
    def __init__(self, client, flash, parent=None):
        super().__init__(parent)
        self.client = client
        self.flash = flash
        self.store = CharacterStore()
        self.loaded_id: str | None = None
        self._installing = False
        self._tree_win = None
        # 되돌리기: 캐릭터별 이전 빌드 XML 스택 / 방금 바꾼 것의 효과
        self._hist: dict[str, list[dict]] = {}
        self._last_change: dict[str, tuple[dict, str]] = {}

        self.strip = TabStrip("캐릭터 가져오기")
        for c in self.store.chars:
            self.strip.add_tab(c["name"])
        tb = self.strip.tabs
        tb.currentChanged.connect(self._on_tab_changed)
        tb.tabMoved.connect(self._on_tab_moved)
        tb.customContextMenuRequested.connect(self._tab_menu)
        self.strip.addRequested.connect(self.open_import)
        self.strip.closeTabRequested.connect(self.delete_char)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(12)

        # 엔진 배너
        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        bh = QHBoxLayout(self.banner)
        bh.setContentsMargins(14, 10, 10, 10)
        bv = QVBoxLayout()
        bv.setSpacing(4)
        self.banner_text = QLabel()
        self.banner_text.setObjectName("BannerText")
        self.banner_text.setWordWrap(True)
        self.banner_bar = QProgressBar()
        self.banner_bar.setTextVisible(False)
        self.banner_bar.setFixedHeight(6)
        self.banner_bar.hide()
        bv.addWidget(self.banner_text)
        bv.addWidget(self.banner_bar)
        bh.addLayout(bv, 1)
        self.banner_btn = QPushButton("PoB 엔진 설치")
        self.banner_btn.setObjectName("Primary")
        self.banner_btn.clicked.connect(self.install_engine)
        bh.addWidget(self.banner_btn)
        root.addWidget(self.banner)

        self.body = QStackedWidget()
        root.addWidget(self.body, 1)
        self.body.addWidget(self._empty_view())
        self.body.addWidget(self._char_view())

        client.stateChanged.connect(self._on_engine_state)
        if hasattr(client, "busyChanged"):
            client.busyChanged.connect(self._on_busy)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._on_engine_state(client.state, "")
        if self.store.chars:
            tb.setCurrentIndex(self.store.current)
            self._on_tab_changed(self.store.current)
        else:
            self.body.setCurrentIndex(0)

    # ================================================================ 뷰 구성
    def _empty_view(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addStretch(1)
        f, cv = card()
        f.setMaximumWidth(560)
        t = QLabel("등록된 캐릭터가 없습니다")
        t.setObjectName("CharName")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d = QLabel(
            "캐릭터를 등록하면 Path of Building 계산 엔진으로 DPS · EHP 를 계산하고,\n"
            "장비를 바꿨을 때 얼마나 강해지는지 바로 비교할 수 있습니다."
        )
        d.setObjectName("CharSub")
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b = QPushButton("+   캐릭터 가져오기")
        b.setObjectName("AddOptionBtn")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(self.open_import)
        cv.addWidget(t)
        cv.addWidget(d)
        cv.addSpacing(8)
        cv.addWidget(b)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(f)
        h.addStretch(1)
        v.addLayout(h)
        v.addStretch(2)
        return w

    def _char_view(self) -> QWidget:
        """위: 캐릭터 + 계산 결과(항상 보임, 바꾼 효과 바로 확인) / 아래: 탭별 내용만 스크롤."""
        outer = QWidget()
        ov = QVBoxLayout(outer)
        ov.setContentsMargins(0, 0, 0, 0)
        ov.setSpacing(8)

        # ---- 고정 영역: 캐릭터 + 계산 결과 ----
        head, hv = card()
        hv.setContentsMargins(16, 10, 16, 10)
        hv.setSpacing(8)
        hh = QHBoxLayout()
        hh.setSpacing(8)
        hv.addLayout(hh)
        left = QVBoxLayout()
        left.setSpacing(1)
        self.c_name = QLabel()
        self.c_name.setObjectName("CharName")
        self.c_sub = QLabel()
        self.c_sub.setObjectName("CharSub")
        self.c_sub.setTextFormat(Qt.TextFormat.RichText)
        nr = QHBoxLayout()
        nr.setSpacing(10)
        nr.addWidget(self.c_name)
        self.busy_label = QLabel("")
        self.busy_label.setStyleSheet("color: #e8b65a; font-size: 9pt;")
        nr.addWidget(self.busy_label)
        nr.addStretch(1)
        left.addLayout(nr)
        left.addWidget(self.c_sub)
        hh.addLayout(left, 2)
        self.refresh_btn = QPushButton("다시 가져오기")
        self.refresh_btn.setToolTip("계정/링크에서 최신 장비·트리·스킬을 다시 받아옵니다")
        self.refresh_btn.clicked.connect(lambda: self.refresh_char())
        code_btn = QPushButton("PoB 코드 복사")
        code_btn.setToolTip("지금 계산에 쓰는 빌드(설정 포함)를 PoB 코드로 복사합니다.\n"
                            "PoB → Import/Export Build → Import from code 에 붙여넣으면 같은 숫자가 나와야 합니다.")
        code_btn.clicked.connect(self.copy_pob_code)
        tree_btn = QPushButton("패시브 트리")
        tree_btn.setObjectName("Primary")
        tree_btn.setToolTip("PoB 처럼 패시브 트리를 찍고 빼면서 DPS · EHP 변화를 확인합니다")
        tree_btn.clicked.connect(self.open_tree)
        more = QPushButton("⋯")
        more.setToolTip("캐릭터 메뉴 (삭제 등)")
        more.setFixedWidth(40)
        mm = QMenu(more)
        mm.addAction("다시 가져오기", self.refresh_char)
        mm.addAction("PoB 코드 복사", self.copy_pob_code)
        mm.addSeparator()
        mm.addAction("이 캐릭터 삭제", lambda: self.delete_char(self.strip.tabs.currentIndex()))
        more.setMenu(mm)
        more.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0; }")
        # 주 스킬 선택 (스킬 · 젬 탭에서도 바꿀 수 있음) — DPS 칸 아래 한 줄에, 칸마다 이름표
        self.main_combo = QComboBox()
        self.main_combo.setToolTip("DPS 를 계산할 스킬 그룹 (PoB 사이드바의 첫 번째 드롭다운)")
        self.main_combo.activated.connect(lambda i: self._set_main(self.main_combo.itemData(i)))
        self.main_combo.setMinimumWidth(160)
        self.main_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.main_combo.setMinimumContentsLength(14)
        self.active_combo = QComboBox()
        self.active_combo.setToolTip("주 그룹 안의 액티브 스킬 (PoB 사이드바의 두 번째 드롭다운)")
        self.active_combo.activated.connect(self._on_active_combo)
        self.part_combo = QComboBox()
        self.part_combo.setToolTip("스킬 파트 (PoB 사이드바의 세 번째 드롭다운)")
        self.part_combo.activated.connect(lambda i: self._call("set_skill_part", {"part": i + 1}, "스킬 파트 변경됨"))
        # 소환수 / 소환수 스킬 (PoB 사이드바와 같음, 소환수가 나오는 주 스킬일 때만 보임)
        self.minion_combo = QComboBox()
        self.minion_combo.setToolTip("소환수 (PoB 사이드바의 Minion)\n예: 면죄는 일반 파수꾼 / 바알 면죄로 승천한 파수꾼")
        self.minion_combo.activated.connect(lambda i: self._call("set_minion", {"index": i + 1}, "소환수 변경됨"))
        self.minion_skill_combo = QComboBox()
        self.minion_skill_combo.setToolTip("소환수가 쓰는 스킬 (PoB 사이드바의 Minion skill)")
        self.minion_skill_combo.activated.connect(
            lambda i: self._call("set_minion_skill", {"index": i + 1}, "소환수 스킬 변경됨"))
        for cb in (self.active_combo, self.part_combo, self.minion_combo, self.minion_skill_combo):
            cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            cb.setMinimumContentsLength(10)
        # 소환수가 나오는 주 스킬(면죄 등)일 때만 보임. 기본 체크
        self.minion_chk = QCheckBox("소환수 DPS 포함")
        self.minion_chk.setToolTip("면죄 · 지배의 일격처럼 소환수가 나오는 스킬은\n"
                                   "소환수 DPS 까지 더해서 주 스킬 DPS 로 보여주고, 장비 비교도 그 기준으로 해요")
        self.minion_chk.setChecked(bool(load_settings().get("minion_in_main", True)))
        self.minion_chk.toggled.connect(self._set_minion_in_main)
        self.minion_chk.hide()
        hh.addStretch(1)
        self.auto_chk = QCheckBox("1분마다 갱신")
        self.auto_chk.setToolTip("체크하면 1분마다 계정에서 최신 레벨·장비·트리를 자동으로 다시 받아옵니다.\n"
                                 "바뀐 게 없으면 다시 계산하지 않고, 앱에서 직접 수정한 빌드는 덮어쓰지 않습니다.")
        self.auto_chk.setChecked(bool(load_settings().get("auto_refresh")))
        self.auto_chk.toggled.connect(self._on_auto_toggled)
        self._auto_timer = QTimer(self, interval=60_000, timeout=self._auto_refresh)
        self._auto_sig: dict[str, str] = {}  # 캐릭터 id → 마지막으로 받은 데이터 지문
        self._auto_busy = False
        self._auto_busy_at = 0.0
        self.auto_lbl = QLabel("")
        self.auto_lbl.setStyleSheet("color: #8a8170; font-size: 8pt;")
        if self.auto_chk.isChecked():
            self._auto_timer.start()
        for b in (tree_btn, self.auto_chk, self.auto_lbl, self.refresh_btn, more):
            hh.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        code_btn.hide()  # ⋯ 메뉴로

        grid = QHBoxLayout()
        grid.setSpacing(8)
        self.tiles = {
            "FullDPS": StatTile("Full DPS", "#ead197"),
            "CombinedDPS": StatTile("주 스킬 DPS", "#ead197"),
            "MinionDPS": StatTile("소환수 DPS", "#c9a6e8"),
            "TotalDPS": StatTile("Hit DPS", "#ead197"),
            "TotalEHP": StatTile("유효 체력 (EHP)", "#8fd0ff"),
            "Life": StatTile("생명력", "#e07a6a"),
            "EnergyShield": StatTile("에너지 보호막", "#9fb5ff"),
            "Mana": StatTile("마나", "#7f9fff"),
            "Speed": StatTile("초당 사용", "#c8a96a"),
            "NetRecovery": StatTile("순 생명력 회복", "#e8794f"),
        }
        self.tiles["NetRecovery"].hide()
        self.tiles["CombinedDPS"].setToolTip("Combined DPS: 주 스킬의 타격 + 도트·점화·중독 합")
        self.tiles["TotalDPS"].setToolTip("타격 DPS 만 (도트·점화·중독 제외)")
        self.tiles["TotalEHP"].setToolTip("계산 설정(Configuration) 기준 유효 체력")
        for t in self.tiles.values():
            grid.addWidget(t, 1)
        hv.addLayout(grid)

        # 계산 기준 스킬 줄: 칸 위에 이름표 (해당 없는 칸은 숨김)
        sk_row = QHBoxLayout()
        sk_row.setSpacing(10)
        self._skill_fields: dict = {}

        def field(caption: str, w, stretch: int, tip: str) -> None:
            box = QWidget()
            bv = QVBoxLayout(box)
            bv.setContentsMargins(0, 0, 0, 0)
            bv.setSpacing(2)
            cap = QLabel(caption)
            cap.setStyleSheet("color: #8a8170; font-size: 8.5pt;")
            cap.setToolTip(tip)
            bv.addWidget(cap)
            bv.addWidget(w)
            sk_row.addWidget(box, stretch)
            self._skill_fields[w] = box

        field("계산할 스킬 그룹", self.main_combo, 3, "DPS 를 계산할 스킬 그룹 (PoB 사이드바 첫 번째 칸)")
        field("그룹 안의 스킬", self.active_combo, 2,
              "그룹 안에 스킬이 여럿일 때 (예: 바알 젬은 바알 쪽 / 일반 쪽)")
        field("스킬 파트", self.part_combo, 2, "스킬의 어느 부분을 계산할지 (예: 투사체 전부 / 하나)")
        field("소환수", self.minion_combo, 2, "계산할 소환수 (예: 면죄는 일반 파수꾼 / 승천한 파수꾼)")
        field("소환수가 쓰는 스킬", self.minion_skill_combo, 2,
              "소환수가 이 스킬만 계속 쓴다고 보고 계산해요 (PoB 와 같음)")
        for w in (self.active_combo, self.part_combo, self.minion_combo, self.minion_skill_combo):
            self._skill_fields[w].hide()  # 계산 결과가 오면 _render_skills 가 필요한 칸만 보이게
        chk_box = QVBoxLayout()
        chk_box.addStretch(1)
        chk_box.addWidget(self.minion_chk)
        sk_row.addLayout(chk_box)
        sk_row.addStretch(1)
        hv.addLayout(sk_row)
        self.res_label = QLabel()
        self.res_label.setObjectName("DefLine")
        self.res_label.setTextFormat(Qt.TextFormat.RichText)
        self.res_label.setWordWrap(True)
        hv.addWidget(self.res_label)
        self.def_label = self.res_label  # (예전 이름 호환)

        # 바꾼 효과 + 되돌리기
        ch = QHBoxLayout()
        ch.setSpacing(8)
        self.delta_label = QLabel()
        self.delta_label.setObjectName("DefLine")
        self.delta_label.setTextFormat(Qt.TextFormat.RichText)
        self.delta_label.setWordWrap(True)
        ch.addWidget(self.delta_label, 1)
        self.undo_btn = QPushButton("↶ 되돌리기")
        self.undo_btn.setToolTip("방금 바꾼 것을 되돌립니다 (Ctrl+Z)")
        self.undo_btn.clicked.connect(self.undo)
        self.orig_btn = QPushButton("가져온 상태로")
        self.orig_btn.setToolTip("여기서 바꾼 장비·젬·트리·설정을 모두 버리고 마지막으로 가져온 빌드로 되돌립니다\n"
                                 "(이것도 되돌리기로 취소할 수 있음)")
        self.orig_btn.clicked.connect(self.revert_orig)
        for b in (self.undo_btn, self.orig_btn):
            b.setStyleSheet("QPushButton { padding: 4px 12px; font-size: 9pt; }")
            ch.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        hv.addLayout(ch)
        ov.addWidget(head)

        # ---- 탭 버튼 ----
        sub = QHBoxLayout()
        sub.setSpacing(6)
        self.sub_btns = []
        tips = ("장착 장비·주얼·플라스크: 빼기/바꾸기/옵션 변경, 각 장비의 기여도",
                "스킬 그룹(주 스킬·사용·Full DPS)과 젬 레벨·퀄리티",
                "PoB Configuration (적 상태, 버프 등)",
                "피하고 싶은 지도 옵션 고르기 → 지도에 Ctrl+C 하면 경고",
                "부위별 DPS 최적 옵션 찾기 (실험 기능)")
        for i, name in enumerate(("장비 · 주얼", "스킬 · 젬", "계산 설정", "지도 옵션", "옵션 최적화 (Beta)")):
            b = QPushButton(name)
            b.setObjectName("SubTab")
            b.setCheckable(True)
            b.setToolTip(tips[i])
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self._set_sub(i))
            b.setStyleSheet("QPushButton#SubTab { padding: 6px 18px; border: 1px solid #2c251c; border-radius: 8px; "
                            "background: #17140f; color: #968b7a; font-size: 10pt; } "
                            "QPushButton#SubTab:checked { background: #2a231a; color: #ead197; border-color: #86704a; } "
                            "QPushButton#SubTab:hover:!checked { color: #ddd5c6; }")
            sub.addWidget(b)
            self.sub_btns.append(b)
        sub.addStretch(1)
        ov.addLayout(sub)

        # ---- 탭 내용 (스크롤) ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll = scroll
        host = QWidget()
        host.setObjectName("ListHost")
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(12)
        self.sub_pages = [QWidget(), QWidget(), QWidget(), QWidget(), QWidget()]
        page_eq = QVBoxLayout(self.sub_pages[0])
        page_gem = QVBoxLayout(self.sub_pages[1])
        page_cfg = QVBoxLayout(self.sub_pages[2])
        page_map = QVBoxLayout(self.sub_pages[3])
        page_beta = QVBoxLayout(self.sub_pages[4])
        for pl in (page_eq, page_gem, page_cfg, page_map, page_beta):
            pl.setContentsMargins(0, 0, 0, 0)
            pl.setSpacing(12)

        from equipment_panel import EquipmentCard

        eq_card, ev = card("장착 장비 · 주얼 · 플라스크")
        self.equip = EquipmentCard(self, ev)
        page_eq.addWidget(eq_card)

        from gems_panel import GemsCard

        gem_card, gmv = card("스킬 그룹 · 젬")
        self.gems = GemsCard(self, gmv)
        page_gem.addWidget(gem_card)

        from beta_panel import BetaCard

        beta_card, bv2 = card("옵션 최적화  ·  Beta")
        self.beta = BetaCard(self, bv2)
        page_beta.addWidget(beta_card)

        from map_avoid_panel import MapAvoidCard

        map_card, mv = card("지도 옵션")
        self.map_avoid = MapAvoidCard(self, mv)
        page_map.addWidget(map_card)

        # PoB Configuration
        cfg_card, gv = card("계산 설정  ·  PoB Configuration 탭과 같은 값")
        self.cfg_info = QLabel()
        self.cfg_info.setObjectName("SectionLabel")
        self.cfg_info.setWordWrap(True)
        self.cfg_info.setTextFormat(Qt.TextFormat.RichText)
        gv.addWidget(self.cfg_info)
        fr = QHBoxLayout()
        fr.setSpacing(8)
        self.cfg_search = QLineEdit()
        self.cfg_search.setPlaceholderText("설정 검색 (예: 감전, 충전, shock)")
        self.cfg_search.setClearButtonEnabled(True)
        self.cfg_search.setMaximumWidth(360)
        self._cfg_timer = QTimer(self, singleShot=True, interval=200,
                                 timeout=lambda: self._render_config((self._cur() or {}).get("summary") or {}))
        self.cfg_search.textChanged.connect(lambda _t: self._cfg_timer.start())
        fr.addWidget(self.cfg_search)
        self.cfg_changed = QCheckBox("기본값과 다른 항목만")
        self.cfg_changed.toggled.connect(lambda _on: self._cfg_timer.start())
        fr.addWidget(self.cfg_changed)
        fr.addStretch(1)
        reset = QPushButton("PoB 기본값으로")
        reset.setToolTip("Configuration 을 PoB 새 빌드의 기본값으로 되돌립니다 (되돌리기로 취소 가능)")
        reset.clicked.connect(lambda: self._call("reset_config", {}, "설정을 PoB 기본값으로 되돌림"))
        fr.addWidget(reset)
        gv.addLayout(fr)
        self.cfg_host = QVBoxLayout()
        self.cfg_host.setSpacing(10)
        gv.addLayout(self.cfg_host)
        self.flask_host = QGridLayout()  # (예전 호환: 플라스크는 장비 탭으로 옮김)
        self.cfg_others = QLabel()
        self.cfg_others.setObjectName("DefLine")
        self.cfg_others.setWordWrap(True)
        self.cfg_others.setTextFormat(Qt.TextFormat.RichText)
        gv.addWidget(self.cfg_others)
        page_cfg.addWidget(cfg_card)

        for w in self.sub_pages:
            v.addWidget(w)
        v.addStretch(1)
        scroll.setWidget(host)
        ov.addWidget(scroll, 1)
        self._set_sub(int(load_settings().get("char_sub_tab", 0)), save=False)
        return outer

    def _set_sub(self, i: int, save: bool = True) -> None:
        i = 0 if i not in (0, 1, 2, 3, 4) else i
        for k, (b, w) in enumerate(zip(self.sub_btns, self.sub_pages)):
            b.setChecked(k == i)
            w.setVisible(k == i)  # 숨긴 쪽은 높이를 차지하지 않음
        self._sub_i = i
        if save and hasattr(self, "scroll"):
            self.scroll.verticalScrollBar().setValue(0)
        if i == 0 and hasattr(self, "equip") and self.equip.impact_stale:
            self.equip._auto.start()
        if i == 2 and getattr(self, "_cfg_dirty", False):
            self._render_config((self._cur() or {}).get("summary") or {})
        if hasattr(self, "gems"):
            self.gems.on_shown(i == 1)
        if hasattr(self, "beta") and i == 4:
            self.beta.on_shown()
        if save:
            s = load_settings()
            s["char_sub_tab"] = i
            save_settings(s)

    # ================================================================ 엔진
    def _on_engine_state(self, st: str, msg: str) -> None:
        if st != "ready":
            self.loaded_id = None
        if self._installing:
            return
        if st == "ready":
            self.banner.hide()
            self.equip.cid = None  # 엔진이 새로 떴으면 장비·기여도 전부 다시
            self._ensure_loaded()
            tw = self._tree_win
            c = self._cur()
            if tw is not None and tw.isVisible() and c is not None:
                tw.bind(c)
            return
        self.banner.show()
        self.banner_bar.hide()
        if st == "missing":
            self.banner_text.setText(
                "DPS · EHP 계산에는 Path of Building 엔진이 필요합니다. "
                "GitHub 에서 PoB 공식 소스(계산용 파일 약 370MB)를 받아 설치합니다."
            )
            self.banner_btn.setText("PoB 엔진 설치")
            self.banner_btn.show()
        elif st == "starting":
            self.banner_text.setText(msg or "PoB 엔진 시작 중…")
            self.banner_btn.hide()
        else:
            self.banner_text.setText(msg or "PoB 엔진이 실행 중이 아닙니다")
            self.banner_btn.setText("엔진 다시 시작")
            self.banner_btn.show()

    def install_engine(self, force_check: bool = False) -> None:
        if self.client.state not in ("missing",) and not force_check:
            self.client.start()
            return
        self._installing = True
        self.banner.show()
        self.banner_btn.hide()
        self.banner_bar.show()
        self.banner_bar.setRange(0, 0)
        self.banner_text.setText("최신 PoB 버전 확인 중…")

        def job(progress):
            tag = installer.latest_tag()
            cur = installer.installed()
            if cur and cur[0] == tag:
                return tag, False
            installer.install(tag, progress)
            return tag, True

        def on_progress(d, t, m):
            self.banner_bar.setRange(0, max(1, t))
            self.banner_bar.setValue(d)
            self.banner_text.setText(m)

        def done(res):
            self._installing = False
            tag, changed = res
            self.flash(f"PoB {tag} {'설치 완료' if changed else '이미 최신 버전'}")
            if changed or self.client.state != "ready":
                self.client.start()
            else:
                self._on_engine_state(self.client.state, "")

        def fail(msg):
            self._installing = False
            self._on_engine_state(self.client.state, "")
            info(self, "PoB 엔진 설치 실패", msg)

        run_async(job, done, fail, on_progress, with_progress=True)

    # ================================================================ 탭 / 캐릭터
    def _cur(self) -> dict | None:
        i = self.strip.tabs.currentIndex()
        return self.store.chars[i] if 0 <= i < len(self.store.chars) else None

    def _on_tab_changed(self, i: int) -> None:
        if not 0 <= i < len(self.store.chars):
            self.body.setCurrentIndex(0)
            return
        self.store.current = i
        self.store.save()
        self.body.setCurrentIndex(1)
        c = self.store.chars[i]
        self._render(c, c.get("summary") or {})
        self._ensure_loaded()
        if self.client.state == "ready":
            self.equip.on_result(c["id"])  # 다른 캐릭터면 장비 목록·기여도 새로
        self.gems.on_summary(c["id"])
        if self._tree_win is not None and self._tree_win.isVisible() and self._tree_win.cid != c["id"]:
            self._tree_win.bind(c)

    def open_tree(self) -> None:
        c = self._cur()
        if c is None:
            return
        if self.client.state not in ("ready", "starting"):
            self.flash("PoB 엔진이 준비되지 않았습니다")
            return
        if self._tree_win is None:
            from tree_view import TreeWindow

            self._tree_win = TreeWindow(self, self.window())
        self._tree_win.bind(c)
        self._tree_win.show()
        self._tree_win.raise_()
        self._tree_win.activateWindow()

    def _on_tab_moved(self, frm: int, to: int) -> None:
        self.store.chars.insert(to, self.store.chars.pop(frm))
        self.store.current = self.strip.tabs.currentIndex()
        self.store.save()

    def _tab_menu(self, pos: QPoint) -> None:
        i = self.strip.tabs.tabAt(pos)
        if i < 0:
            return
        self.strip.tabs.setCurrentIndex(i)
        m = QMenu(self)
        m.addAction("다시 가져오기", self.refresh_char)
        m.addSeparator()
        m.addAction("삭제", lambda: self.delete_char(i))
        m.exec(self.strip.tabs.mapToGlobal(pos))

    def _ensure_loaded(self) -> None:
        c = self._cur()
        if c is None or self.client.state != "ready" or self.loaded_id == c["id"]:
            return
        xml = self.store.xml(c["id"])
        if not xml:
            self.flash("저장된 빌드 데이터가 없습니다. 다시 가져오기를 해주세요.")
            return
        cid = c["id"]
        self.loaded_id = cid
        self.flash(f"{c['name']} 계산 중…")
        self.client.call("load_xml", {"xml": xml, "name": c["name"]},
                         lambda r: self._apply_result(cid, r, record=False), self._on_call_err)

    def _apply_result(self, cid: str, r: dict, flash: str = "", record: bool = True) -> None:
        """계산 결과 반영. record=True 면 바뀌기 전 빌드를 되돌리기 목록에 넣고 '방금 바꾼 효과'를 표시."""
        c = next((x for x in self.store.chars if x["id"] == cid), None)
        if c is None:
            return
        old_stats = (c.get("summary") or {}).get("stats") or {}
        c["summary"] = r.get("summary") or {}
        new_xml = r.get("xml")
        if new_xml:
            old_xml = self.store.xml(cid)
            if not self.store.orig_xml(cid) and record and old_xml and old_stats:
                self.store.set_orig(cid, old_xml)
                c["orig_stats"] = old_stats
            if record and old_xml and old_xml != new_xml:
                h = self._hist.setdefault(cid, [])
                h.append({"xml": old_xml, "msg": flash or "변경", "clean": not c.get("modified")})
                del h[:-40]
                self._last_change[cid] = (old_stats, flash or "변경")
                c["modified"] = True  # 가져온 상태와 다름 (XML 문자열 비교는 PoB 저장 순서가 달라 못 믿음)
            self.store.set_xml(cid, new_xml)
            if not self.store.orig_xml(cid):
                # 예전 버전에서 등록한 캐릭터: 처음 계산한 상태를 '가져온 상태' 기준으로
                self.store.set_orig(cid, new_xml)
                c["orig_stats"] = (c["summary"] or {}).get("stats") or {}
        self.store.save()
        if self._cur() is c:
            self._render(c, c["summary"])
        tw = self._tree_win
        if tw is not None and tw.isVisible() and tw.cid == cid:
            tw.on_summary()
        if self._cur() is c:
            self.equip.on_result(cid)
            self.gems.on_summary(cid)
        self.flash(flash or f"{c['name']} 계산 완료")

    # ---------------------------------------------------------------- 되돌리기
    def _reload(self, cid: str, xml: str, msg: str, record: bool, before: dict | None,
                clear_modified: bool = False) -> None:
        c = next((x for x in self.store.chars if x["id"] == cid), None)
        if c is None or self.client.state != "ready":
            return
        self.loaded_id = cid
        self.equip.cid = None  # 장비·기여도 전부 다시

        def ok(r):
            self._apply_result(cid, r, msg, record=record)
            if clear_modified:
                c["modified"] = False
                self.store.save()
                if self._cur() is c:
                    self._render_delta(c)
            if not record and before is not None:
                self._last_change[cid] = (before, msg)
                if self._cur() is c:
                    self._render_delta(c)
            tw = self._tree_win
            if tw is not None and tw.isVisible() and tw.cid == cid:
                tw.bind(c)

        self.client.call("load_xml", {"xml": xml, "name": c["name"]}, ok, self._on_call_err)

    def undo(self) -> None:
        c = self._cur()
        h = self._hist.get(c["id"]) if c else None
        if not h or self.client.state != "ready":
            self.flash("되돌릴 변경이 없습니다")
            return
        e = h.pop()
        before = (c.get("summary") or {}).get("stats") or {}
        self._reload(c["id"], e["xml"], f"되돌림: {e['msg']}", False, before, clear_modified=bool(e.get("clean")))

    def revert_orig(self) -> None:
        c = self._cur()
        xml = self.store.orig_xml(c["id"]) if c else None
        if not xml:
            self.flash("가져온 상태가 저장되어 있지 않습니다")
            return
        if not c.get("modified"):
            self.flash("이미 가져온 상태입니다")
            return
        self._reload(c["id"], xml, "가져온 상태로 되돌림", True, None, clear_modified=True)

    def _render_delta(self, c: dict) -> None:
        from statfmt import change_cells

        st = (c.get("summary") or {}).get("stats") or {}
        out = []
        lc = self._last_change.get(c["id"])
        if lc:
            cells = change_cells(lc[0], st)
            out.append(f"<span style='color:#c8a96a'>방금</span> <span style='color:{DIM}'>{html.escape(lc[1])}</span>"
                       f" &nbsp;" + (" · ".join(cells) if cells else f"<span style='color:{DIM}'>수치 변화 없음</span>"))
        orig = c.get("orig_stats")
        modified = bool(orig) and bool(c.get("modified")) and self.store.orig_xml(c["id"]) is not None
        if modified:
            cells = change_cells(orig, st)
            out.append(f"<span style='color:#c8a96a'>가져온 상태 대비</span> &nbsp;"
                       + (" · ".join(cells) if cells else f"<span style='color:{DIM}'>수치 같음</span>"))
        if not out:
            out.append(f"<span style='color:{DIM}'>장비·젬·트리·설정을 바꾸면 여기에 바로 바뀐 양이 나옵니다. "
                       f"모든 변경은 되돌리기(Ctrl+Z)로 취소할 수 있습니다.</span>")
        self.delta_label.setText("<br>".join(out))
        n = len(self._hist.get(c["id"]) or [])
        self.undo_btn.setEnabled(n > 0 and self.client.state == "ready")
        self.undo_btn.setText(f"↶ 되돌리기{f' ({n})' if n else ''}")
        h = self._hist.get(c["id"])
        self.undo_btn.setToolTip(f"되돌리기: {h[-1]['msg']} (Ctrl+Z)" if h else "되돌릴 변경 없음")
        self.orig_btn.setEnabled(modified and self.client.state == "ready")

    def _on_busy(self, busy: bool) -> None:
        # 짧은 계산은 깜빡이지 않게 0.3초 넘게 걸릴 때만 표시
        if not hasattr(self, "_busy_timer"):
            self._busy_timer = QTimer(self, singleShot=True, interval=300,
                                      timeout=lambda: self.busy_label.setText("● 계산 중…"))
        if busy:
            self._busy_timer.start()
        else:
            self._busy_timer.stop()
            self.busy_label.setText("")

    def _on_call_err(self, msg: str) -> None:
        self.loaded_id = None
        self.flash(f"PoB 계산 오류: {msg}")

    def open_import(self) -> None:
        if self.client.state == "missing":
            if confirm(self, "PoB 엔진 필요", "캐릭터를 계산하려면 먼저 PoB 엔진을 설치해야 합니다.\n지금 설치할까요?", "설치"):
                self.install_engine()
            return
        settings = load_settings()
        dlg = ImportDialog(settings, self.window())
        ok = dlg.exec()
        save_settings(settings)
        if not ok:
            return
        self._import_payload(dlg.kind, dlg.payload, dlg.name, dlg.source, None)

    def _import_payload(self, kind: str, payload: str, name: str, source: dict, existing_id: str | None,
                        quiet: bool = False, after=None) -> None:
        cmd, args = ("load_character", {"json": payload}) if kind == "json" else ("load_xml", {"xml": payload})
        if kind == "json" and existing_id:
            prev = self.store.xml(existing_id)
            if prev:
                args["prev_xml"] = prev  # Full DPS·젬 사용·설정·플라스크 등 사용자가 고른 것 유지
        if not quiet:
            self.flash("PoB 로 빌드 계산 중…")

        def ok(r):
            s = r.get("summary") or {}
            nm = name or f"{s.get('ascendClassName') or s.get('className') or 'PoB 빌드'} Lv{s.get('level', '?')}"
            if existing_id:
                c = next((x for x in self.store.chars if x["id"] == existing_id), None)
                if c is None:
                    return
                c["source"] = source
                c.pop("tree_orig", None)  # 새로 받은 트리가 비교 기준
                self.loaded_id = existing_id
                if r.get("xml"):
                    self.store.set_orig(existing_id, r["xml"])  # 새로 받은 빌드가 '가져온 상태'
                    c["orig_stats"] = s.get("stats") or {}
                self._apply_result(existing_id, r, f"{c['name']} {'자동 갱신됨' if quiet else '다시 가져오기 완료'}")
                c["modified"] = False
                self.store.save()
                if self._cur() is c:
                    self._render_delta(c)
                if after:
                    after(True)
                return
            c = self.store.add(nm, source, r.get("xml", ""), s)
            if r.get("xml"):
                self.store.set_orig(c["id"], r["xml"])
                c["orig_stats"] = s.get("stats") or {}
                self.store.save()
            self.loaded_id = c["id"]
            self.strip.add_tab(nm)
            self.strip.tabs.setCurrentIndex(len(self.store.chars) - 1)
            self._on_tab_changed(len(self.store.chars) - 1)
            self.flash(f"{nm} 등록 완료")

        def err(msg):
            self.loaded_id = None
            if after:
                after(False, str(msg))
            if quiet:
                self.flash(f"자동 갱신 계산 실패: {msg}")
                return
            info(self, "가져오기 실패", f"PoB 가 빌드를 계산하지 못했습니다.\n{msg}")

        self.client.call(cmd, args, ok, err)

    @staticmethod
    def _data_sig(js: str) -> str:
        """경험치처럼 계속 바뀌는 값은 빼고 계산에 쓰이는 부분만으로 지문을 만든다."""
        import hashlib
        import json

        try:
            d = json.loads(js).get("character") or {}
        except ValueError:
            return js
        keep = {k: d.get(k) for k in ("level", "class", "classId", "ascendancyClass", "league",
                                      "passives", "equipment", "jewels", "guardian")}
        return hashlib.md5(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def _build_core(xml: str):
        """빌드에서 '다시 가져오면 사라지는 것'만 뽑음: 레벨·직업·도적·판테온·트리·장착 장비·젬 구성.
        젬/그룹 켜기·끄기, Full DPS, 주 스킬, 설정, 플라스크 켜기는 다시 가져와도 유지되므로 뺀다."""
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml)
        b = root.find("Build")
        out: list = [tuple((b.get(k) or "") for k in ("level", "className", "ascendClassName", "bandit",
                                                      "pantheonMajorGod", "pantheonMinorGod")) if b is not None else ()]
        items_el = root.find("Items")
        texts: dict[str, str] = {}
        if items_el is not None:
            for it in items_el.findall("Item"):
                t = "\n".join(ln.strip() for ln in (it.text or "").splitlines() if ln.strip())
                texts[it.get("id") or ""] = t
            sets = {s.get("id"): s for s in items_el.findall("ItemSet")}
            st = sets.get(items_el.get("activeItemSet")) or next(iter(sets.values()), None)
            if st is not None:
                out.append(sorted((s.get("name") or "", texts.get(s.get("itemId") or "", ""))
                                  for s in st.findall("Slot") if (s.get("itemId") or "0") != "0"))
        tree = root.find("Tree")
        if tree is not None:
            specs = tree.findall("Spec")
            try:
                sp = specs[int(tree.get("activeSpec") or 1) - 1]
            except (ValueError, IndexError):
                sp = specs[0] if specs else None
            if sp is not None:
                out.append(tuple(sp.get(k) or "" for k in ("classId", "ascendClassId", "secondaryAscendClassId")))
                out.append(sorted((sp.get("nodes") or "").split(",")))
                out.append(sorted((sp.get("masteryEffects") or "").split(",")))
                so = sp.find("Sockets")
                out.append(sorted((s.get("nodeId") or "", texts.get(s.get("itemId") or "", ""))
                                  for s in (so.findall("Socket") if so is not None else [])
                                  if (s.get("itemId") or "0") != "0"))
        sk = root.find("Skills")
        if sk is not None:
            sets = {s.get("id"): s for s in sk.findall("SkillSet")}
            ss = sets.get(sk.get("activeSkillSet")) or next(iter(sets.values()), None)
            groups = ss.findall("Skill") if ss is not None else sk.findall("Skill")
            out.append(sorted(
                (g.get("slot") or "", tuple((x.get("skillId") or x.get("nameSpec") or "", x.get("level") or "",
                                             x.get("quality") or "", x.get("qualityId") or "")
                                            for x in g.findall("Gem")))
                for g in groups))
        return out

    def _edited(self, c: dict) -> bool:
        """앱에서 장비·트리·젬 구성 등을 바꿔서, 다시 가져오면 그 수정이 사라지는가?
        (젬 켜기·끄기, Full DPS, 설정, 플라스크 같은 것만 바꿨으면 False → 자동 갱신 계속)"""
        if not c.get("modified"):
            return False
        cur, orig = self.store.xml(c["id"]), self.store.orig_xml(c["id"])
        if not cur or not orig:
            return True
        try:
            return self._build_core(cur) != self._build_core(orig)
        except Exception:  # noqa: BLE001 - 못 읽으면 안전하게 '수정됨'
            return True

    def _on_auto_toggled(self, on: bool) -> None:
        s = load_settings()
        s["auto_refresh"] = bool(on)
        save_settings(s)
        if on:
            self._auto_timer.start()
            self.flash("1분마다 자동 갱신 켜짐")
            self._auto_refresh()
        else:
            self._auto_timer.stop()
            self.auto_lbl.setText("")
            self.flash("자동 갱신 꺼짐")

    def _auto_status(self, text: str, tip: str = "") -> None:
        """체크박스 옆에 마지막 자동 갱신 결과 표시 + 로그 (%LOCALAPPDATA%\\ExileDelta\\auto_refresh.log)."""
        import os
        import time as _t

        now = _t.strftime("%H:%M")
        self.auto_lbl.setText(f"{now} {text}")
        self.auto_lbl.setToolTip(tip or text)
        try:
            from paths import LOCAL

            d = str(LOCAL)
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, "auto_refresh.log")
            if os.path.exists(p) and os.path.getsize(p) > 200_000:
                os.replace(p, p + ".old")
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"{_t.strftime('%Y-%m-%d %H:%M:%S')} {text}{' | ' + tip if tip and tip != text else ''}\n")
        except OSError:
            pass

    def _auto_refresh(self) -> None:
        import time as _t

        c = self._cur()
        if c is None:
            return self._auto_status("캐릭터 없음")
        if self._auto_busy:
            if _t.monotonic() - self._auto_busy_at < 180:
                return self._auto_status("이전 요청 기다리는 중")
            self._auto_busy = False  # 3분 넘게 응답 없으면 막힌 것으로 보고 다시 시도
        if self.client.state != "ready":
            return self._auto_status("건너뜀: 엔진 준비 중", f"PoB 엔진 상태: {self.client.state}")
        if self.client.fg_pending():
            return self._auto_status("건너뜀: 계산 중", "다른 계산이 진행 중이라 다음 회차에 확인합니다")
        if (c.get("source") or {}).get("type") != "account":
            return self._auto_status("대상 아님", "PoB 코드/링크로 등록한 캐릭터는 자동 갱신하지 않습니다")
        if self._edited(c):
            # 앱에서 장비·트리를 직접 바꾼 빌드는 덮어쓰지 않음 → 멈춘 이유를 보여 줌
            # (젬 켜기·끄기, Full DPS, 설정, 플라스크 켜기만 바꾼 건 다시 가져와도 유지되니 계속 갱신)
            return self._auto_status("일시정지: 장비·트리를 직접 수정함",
                                     "앱에서 장비·패시브 트리·젬 구성 등을 바꿔서 덮어쓰지 않고 있습니다.\n"
                                     "'가져온 상태로 되돌림' 또는 '다시 가져오기'를 누르면 자동 갱신이 다시 이어집니다.")
        why = importers.budget_note()
        if why:
            return self._auto_status(why, "pathofexile.com 은 IP 마다 요청 횟수 한도가 있어(넘기면 최대 1시간 차단)\n"
                                          "한도에 가까우면 자동 갱신을 잠시 쉽니다. 시간이 지나면 저절로 이어집니다.")
        self.refresh_char(auto=True)

    def refresh_char(self, auto: bool = False) -> None:
        c = self._cur()
        if c is None:
            return
        src = c.get("source") or {}
        if src.get("type") == "account":
            ch = src["character"]
            if not auto:
                self.flash(f"{c['name']} 최신 정보 받는 중…")
            import time as _t

            self._auto_busy = True
            self._auto_busy_at = _t.monotonic()

            def got(res):
                self._auto_busy = False
                cur, js = res
                sig = self._data_sig(js)
                if auto and self._auto_sig.get(c["id"]) == sig:
                    return self._auto_status(f"확인 · 변경 없음 (Lv {cur.get('level')})")
                if auto and self._edited(c):
                    return self._auto_status("일시정지: 장비·트리를 직접 수정함")
                old_lv = (c.get("summary") or {}).get("level")
                nsrc = dict(src, character=cur)  # 레벨·직업·리그를 최신으로
                lv = cur.get("level")

                def applied(ok_: bool, msg: str = "") -> None:
                    if ok_:
                        self._auto_sig[c["id"]] = sig  # 계산까지 성공했을 때만 '받은 것'으로 기록
                        if auto:
                            self._auto_status(f"갱신됨 (Lv {old_lv}→{lv})" if old_lv != lv else f"갱신됨 (Lv {lv})")
                    elif auto:
                        self._auto_status("계산 실패 — 다음 회차에 다시", msg)

                self._import_payload("json", js, c["name"], nsrc, c["id"], quiet=auto, after=applied)

            def fail(m):
                self._auto_busy = False
                if auto:
                    self._auto_status("받기 실패 — 다음 회차에 다시", m)
                else:
                    info(self, "다시 가져오기 실패", m)

            run_async(lambda: importers.refetch_character(src["account"], src["realm"], ch, auto=auto), got, fail)
        elif src.get("link"):
            self.flash(f"{c['name']} 링크에서 다시 받는 중…")
            run_async(
                lambda: importers.resolve_code_or_link(src["link"]),
                lambda res: self._import_payload("xml", res[0], c["name"], src, c["id"]),
                lambda m: info(self, "다시 가져오기 실패", m),
            )
        else:
            info(self, "다시 가져오기", "PoB 코드로 등록한 캐릭터는 새 코드로 다시 등록해 주세요.")

    def delete_char(self, i: int) -> None:
        if not 0 <= i < len(self.store.chars):
            return
        c = self.store.chars[i]
        if not confirm(self, "캐릭터 삭제", f"'{c['name']}' 캐릭터를 삭제할까요?", "삭제", danger=True):
            return
        tb = self.strip.tabs
        tb.blockSignals(True)
        self.store.remove(i)
        tb.removeTab(i)
        tb.blockSignals(False)
        if self.loaded_id == c["id"]:
            self.loaded_id = None
        self._on_tab_changed(tb.currentIndex())
        self.flash(f"'{c['name']}' 삭제됨")

    # ================================================================ 렌더
    def _render(self, c: dict, s: dict) -> None:
        st = s.get("stats") or {}
        self.c_name.setText(c["name"])
        cls = s.get("ascendClassName") or ""
        base = s.get("className") or ""
        cls_txt = f"{cls} ({base})" if cls and cls != "None" else base
        src = c.get("source") or {}
        if src.get("type") == "account":
            ch = src.get("character") or {}
            src_txt = f"pathofexile.com · {src.get('account')} · {ch.get('league', '')}"
            self.refresh_btn.setEnabled(True)
        else:
            src_txt = f"PoB 코드 · {src.get('link') or '직접 입력'}"
            self.refresh_btn.setEnabled(bool(src.get("link")))
        head = f"Lv {s.get('level', '?')}  ·  {html.escape(cls_txt)}" if s else "PoB 엔진 대기 중…"
        self.c_sub.setText(f"{head} &nbsp;<span style='color:#62594d; font-size:8.5pt'>{html.escape(src_txt)}</span>")

        import skillnames

        en_main = s.get("mainSkillName") or ""
        if (s.get("ascend") or {}).get("on"):  # 바알 면죄(승천한 파수꾼) 로 계산 중
            en_main = "Vaal " + en_main if skillnames.ko("Vaal " + en_main) != "Vaal " + en_main else en_main
        main_name = skillnames.ko(en_main)
        n_full = sum(1 for g in (s.get("groups") or []) if g.get("includeInFullDPS"))
        for k, tile in self.tiles.items():
            v = st.get(k)
            sub = ""
            if k == "NetRecovery":
                # 정의의 화염 · 피의 격노 등 스스로 받는 지속 피해가 있을 때만: 그 피해를 받는 쪽의 순 회복 (PoB Net Recovery 값)
                from statfmt import _pool, degen_label, degen_pools, has_degen, net_regen, set_degen_sources

                set_degen_sources(s.get("degenSources"))
                on = bool(st) and has_degen(st)
                tile.setVisible(on)
                if not on:
                    continue
                pools = degen_pools(st) or ["Life"]
                v = net_regen(st, pools[0])
                nm, _ = _pool(pools[0])
                tile.t.setText(f"순 {nm} 회복")
                lab = degen_label()
                sub = f"{lab} -{st.get('TotalBuildDegen') or 0:,.0f}/초"
                rows = [f"{lab}: 스스로 받는 피해 {st.get('TotalBuildDegen') or 0:,.1f}/초"]
                srcs = s.get("degenSources") or []
                if len(srcs) > 1:
                    from statfmt import _src_ko
                    rows += [f"  · {_src_ko(e)} {e.get('value', 0):,.1f}/초 (증감 적용 전)" for e in srcs]
                for p in pools:
                    rows.append(f"순 {_pool(p)[0]} 회복 {net_regen(st, p) or 0:+,.1f}/초")
                if st.get("TotalNetRegen") is not None:
                    rows.append(f"전체 순 회복 {st['TotalNetRegen']:+,.1f}/초")
                tile.setToolTip("\n".join(rows) + "\n(PoB 사이드바 Net Recovery 와 같은 값)")
                tile.set(f"{v:+,.0f}/초" if v is not None else "—", sub)
                tile.v.setStyleSheet(f"color: {'#e0644c' if (v or 0) < 0 else '#e8794f'};")
                continue
            if k == "CombinedDPS":
                sub = main_name
                md = st.get("MinionDPS")
                self.minion_chk.setVisible(bool(md))
                if md:  # 소환수를 부르는 주 스킬 (면죄 등)
                    mname = skillnames.ko(s.get("minionName") or "") or "소환수"
                    if s.get("minionInMain", True):
                        sub = f"{main_name} + 소환수"
                        tile.setToolTip(f"주 스킬 DPS = 스킬 {fmt_big(st.get('PlayerDPS'))} + {mname} {fmt_big(md)}\n"
                                        "위쪽 '소환수 DPS 포함' 체크를 끄면 스킬 DPS 만 봐요")
                    else:
                        tile.setToolTip(f"소환수({mname}) DPS {fmt_big(md)} 는 빠져 있어요\n"
                                        "위쪽 '소환수 DPS 포함' 체크를 켜면 더해져요")
                else:
                    tile.setToolTip("Combined DPS: 주 스킬의 타격 + 도트·점화·중독 합")
            elif k == "MinionDPS":
                # 소환수가 나오는 주 스킬일 때만: 고른 소환수 · 소환수 스킬 기준
                tile.setVisible(bool(v))
                ms, mk = s.get("minions") or [], s.get("minionSkills") or []
                mn = ms[s["minionSel"] - 1] if 0 < int(s.get("minionSel") or 0) <= len(ms) else (s.get("minionName") or "")
                sk = mk[s["minionSkillSel"] - 1] if 0 < int(s.get("minionSkillSel") or 0) <= len(mk) else ""
                mn, sk = skillnames.ko(mn), skillnames.ko(sk)
                sub = sk or mn  # 소환수 이름은 위 드롭다운에 보이니 칸에는 스킬만 (길어서 잘림)
                tile.setToolTip(f"{' · '.join(x for x in (mn, sk) if x)} 기준 DPS\n위쪽 드롭다운에서 소환수 · 소환수 스킬을 바꿀 수 있어요")
            elif k == "TotalDPS":
                sub = "도트·점화·중독 제외"
            elif k == "FullDPS":
                sub = f"스킬 {n_full}개 합산"
                # Full DPS 에 넣은 스킬이 없으면 0 이라 의미 없음 → 숨김 (스킬 · 젬 탭에서 체크)
                tile.setVisible(bool(v))
                sd = s.get("skillDPS") or []
                tile.setToolTip("Full DPS 구성\n" + "\n".join(
                    f"{x.get('name')}{' x' + str(x['count']) if x.get('count', 1) > 1 else ''}  {fmt_big(x.get('dps'))}"
                    for x in sd) if sd else "Full DPS 에 포함된 스킬 없음")
            elif k == "TotalEHP":
                sub = "계산 설정 기준"
            elif k == "Life" and v is not None and st.get("LifeUnreserved") is not None and st.get("LifeUnreserved") != v:
                sub = f"예약 후 {fmt_big(st['LifeUnreserved'])}"
            elif k == "EnergyShield":
                tile.setVisible(bool(v) or not st)
            elif k == "Mana" and v is not None and st.get("ManaUnreserved") is not None and st.get("ManaUnreserved") != v:
                sub = f"예약 후 {fmt_big(st['ManaUnreserved'])}"
            tile.set(fmt_big(v) if v is not None else "—", sub)

        def res(key, label, color):
            v = st.get(key)
            if v is None:
                return ""
            warn = " <span style='color:#e0644c'>▼</span>" if key != "ChaosResist" and v < 75 else ""
            return f"<span style='color:{color}'>{label}</span> <b>{v:.0f}%</b>{warn}"

        line1 = "&nbsp;&nbsp;".join(filter(None, [
            res("FireResist", "화염", "#e8794f"), res("ColdResist", "냉기", "#7fb4ff"),
            res("LightningResist", "번개", "#f2d36b"), res("ChaosResist", "카오스", "#c77ad6"),
        ]))
        parts = []
        for key, label in (("Armour", "방어도"), ("Evasion", "회피"), ("EffectiveSpellSuppressionChance", "주문 억제"),
                           ("EffectiveBlockChance", "막기"), ("EffectiveSpellBlockChance", "주문 막기")):
            if st.get(key):
                unit = "%" if "Chance" in key else ""
                parts.append(f"<span style='color:{DIM}'>{label}</span> <b>{fmt_big(st[key])}{unit}</b>")
        if parts:
            line1 += " &nbsp;<span style='color:#4a4032'>|</span>&nbsp; " + " &nbsp;".join(parts)
        from statfmt import MH

        hits = [f"<span style='color:{col}'>{lab}</span> {fmt_big(st[k])}" for lab, k, col in MH if st.get(k) is not None]
        if hits:
            line1 += f"<br><span style='color:{DIM}'>최대 피격</span>&nbsp; " + "&nbsp;&nbsp;".join(hits)
        self.res_label.setText(line1)
        self._render_delta(c)
        self._render_skills(s)
        # 설정 탭은 항목이 많아 보일 때만 다시 그림
        self._cfg_dirty = True
        if getattr(self, "_sub_i", 0) == 2:
            self._render_config(s)
        self._render_config(s)

    def _render_config(self, s: dict) -> None:
        def clear(layout):
            while layout.count():
                it = layout.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()

        self._cfg_dirty = False
        clear(self.cfg_host)
        cfg = s.get("config") or {}
        ready = self.client.state == "ready"
        sections = [x for x in (cfg.get("sections") or []) if isinstance(x, dict)]
        n_changed = sum(1 for sec in sections for it in _items(sec) if it.get("changed"))
        self.cfg_info.setText(
            f"계산 엔진: <b>Path of Building {html.escape(str(s.get('pobVersion', '?')))}</b>"
            f" &nbsp;·&nbsp; 기본값과 다른 항목 <b style='color:#e8b65a'>{n_changed}</b>개 (금색)"
            f"<br><span style='color:{DIM}'>PoB 처럼 이 빌드에 관련된 항목만 보입니다. "
            f"적 기준(Enemy Stats)은 PoB 기본값 고정. 마우스를 올리면 PoB 원문 설명이 보입니다.</span>")
        q = self.cfg_search.text().strip().lower()
        only_changed = self.cfg_changed.isChecked()
        shown_any = False
        for sec in sections:
            items = _items(sec)
            if q or only_changed:
                items = self._filter_config(items, q, only_changed)
            if not items:
                continue
            shown_any = True
            box = QFrame()
            box.setObjectName("ConfigSection")
            bv = QVBoxLayout(box)
            bv.setContentsMargins(12, 10, 12, 10)
            bv.setSpacing(6)
            title = QLabel(f"{config_ko.section(sec['name'])}  <span style='color:{DIM}; font-weight:normal'>"
                           f"· {html.escape(sec['name'])}</span>")
            title.setObjectName("CardTitle")
            title.setTextFormat(Qt.TextFormat.RichText)
            bv.addWidget(title)
            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(5)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(2, 1)
            bv.addLayout(grid)
            self._fill_config_grid(grid, items, ready)
            self.cfg_host.addWidget(box)
        if not sections:
            self.cfg_host.addWidget(QLabel("PoB 엔진에서 설정을 읽는 중…"))
        elif not shown_any:
            e = QLabel("조건에 맞는 설정이 없습니다")
            e.setObjectName("SectionLabel")
            self.cfg_host.addWidget(e)

        locked = [x for x in (cfg.get("locked") or []) if isinstance(x, dict)]
        if locked:
            self.cfg_others.setText(
                f"<span style='color:{DIM}'>이 빌드에 들어 있는 적 기준 설정 (PoB 코드에서 가져온 값, 여기서는 변경 불가)</span><br>"
                + " &nbsp;·&nbsp; ".join(
                    f"{html.escape(x['label'])} <b>{html.escape(str(x['value']))}</b>" for x in locked))
        else:
            self.cfg_others.setText("")

    @staticmethod
    def _filter_config(items: list, q: str, only_changed: bool) -> list:
        """검색어(한글·영문 이름) / 바꾼 항목만. 하위 옵션은 부모와 함께 보이게."""
        def hit(it):
            if it.get("type") == "label" or not it.get("var"):
                return False
            if only_changed and not it.get("changed"):
                return False
            if q:
                return q in config_ko.label(it["label"]).lower() or q in str(it["label"]).lower()
            return True

        keep = {it["var"] for it in items if hit(it)}
        for it in items:  # 부모 ↔ 하위 옵션 같이
            p = it.get("parent")
            if p and it.get("var") in keep:
                keep.add(p)
        for it in items:
            if it.get("parent") in keep and it.get("var"):
                keep.add(it["var"])
        return [it for it in items if it.get("var") in keep]

    def _fill_config_grid(self, grid: QGridLayout, items: list, ready: bool) -> None:
        """2단 배치. 소제목(label)은 한 줄 전체, 체크/숫자/목록은 칸 하나씩.

        PoB 의 하위 옵션(ifOption: 예 '적이 냉각 상태인가?' → '냉각 효과')은 따로 칸을 차지하지 않고
        부모 칸 안(체크 오른쪽)에 붙인다. 체크할 때마다 칸이 하나씩 밀려 옆 옵션 위치가 바뀌던 문제 방지.
        """
        row, col = 0, 0
        vars_here = {it.get("var") for it in items if it.get("var")}
        children: dict[str, list] = {}
        for it in items:
            p = it.get("parent")
            if p and p in vars_here and it.get("var"):
                children.setdefault(p, []).append(it)

        def next_cell():
            nonlocal row, col
            r, c = row, col
            col += 1
            if col > 1:
                row, col = row + 1, 0
            return r, c

        def tip(it):
            t = f"PoB: {it['label']}"
            if it.get("tooltip"):
                t += "\n\n" + it["tooltip"]
            return t

        def text_of(it):
            text = config_ko.label(it["label"])
            if not it.get("shown"):
                text += "  (현재 빌드에 해당 없음)"
            return text

        def gold(it):
            return "color: #e8b65a; font-weight: bold;" if it.get("changed") else ""

        def input_widget(it):
            kind, var = it.get("type"), it["var"]
            if kind == "list":
                w = QComboBox()
                opts = it.get("list") if isinstance(it.get("list"), list) else []
                for o in opts:
                    w.addItem(config_ko.option(str(o.get("label"))), o.get("val"))
                cur = it.get("value")
                if cur is None:
                    cur = it.get("default")
                w.setCurrentIndex(next((i for i, o in enumerate(opts) if o.get("val") == cur), 0))
                w.activated.connect(lambda i, v=var, w=w: self._call(
                    "set_config", {"var": v, "value": w.itemData(i)}, "설정 변경됨"))
                w.setMaximumWidth(260)
            else:
                w = QLineEdit()
                w.setFixedWidth(90)
                v = it.get("value")
                w.setText("" if v is None or v is False else fmt_plain(v))
                ph = it.get("placeholder")
                w.setPlaceholderText("" if ph is None else fmt_plain(ph))
                w.setValidator(QDoubleValidator() if kind == "float" else QIntValidator(-999999, 99999999))
                w.editingFinished.connect(lambda w=w, v=var, k=kind: self._set_number(v, k, w.text()))
            w.setToolTip(tip(it))
            w.setEnabled(ready)
            return w

        def add_children(cell, parent_var: str) -> None:
            """하위 옵션: 부모 칸 안, 한 단 들여서 아래쪽에 (칸 수가 바뀌지 않음)."""
            for ch in children.get(parent_var, []):
                if not (ch.get("shown") or ch.get("changed")) or ch.get("type") == "check":
                    continue
                sub = QHBoxLayout()
                sub.setContentsMargins(26, 0, 0, 0)
                sub.setSpacing(8)
                lab = QLabel("└ " + config_ko.label(ch["label"]))
                lab.setStyleSheet(gold(ch) or f"color: {DIM};")
                lab.setToolTip(tip(ch))
                sub.addWidget(lab)
                sub.addWidget(input_widget(ch))
                sub.addStretch(1)
                cell.addLayout(sub)

        child_vars = {ch["var"] for lst in children.values() for ch in lst if ch.get("type") != "check"}
        for it in items:
            kind = it.get("type")
            if kind == "label":
                if col:
                    row, col = row + 1, 0
                lab = QLabel(config_ko.label(it["label"], "label"))
                lab.setObjectName("ConfigSub")
                lab.setToolTip(it["label"])
                grid.addWidget(lab, row, 0, 1, 4)
                row += 1
                continue
            var = it.get("var")
            if not var or var in child_vars:
                continue  # 하위 옵션은 부모 칸 안에 붙임
            r, c = next_cell()
            outer = QVBoxLayout()
            outer.setSpacing(3)
            cell = QHBoxLayout()
            cell.setSpacing(8)
            outer.addLayout(cell)
            if kind == "check":
                w = QCheckBox(text_of(it))
                w.setChecked(bool(it.get("value")))
                w.setStyleSheet(gold(it))
                w.toggled.connect(lambda on, v=var: self._call("set_config", {"var": v, "value": on}, "설정 변경됨"))
                w.setToolTip(tip(it))
                w.setEnabled(ready)
                cell.addWidget(w)
                cell.addStretch(1)
            else:
                lab = QLabel(text_of(it))
                lab.setWordWrap(True)
                lab.setStyleSheet(gold(it))
                lab.setToolTip(tip(it))
                cell.addWidget(lab, 1)
                cell.addWidget(input_widget(it))
            add_children(outer, var)
            grid.addLayout(outer, r, c * 2, 1, 2, Qt.AlignmentFlag.AlignTop)
    def _set_number(self, var: str, kind: str, text: str) -> None:
        text = text.strip()
        value = None
        if text:
            try:
                value = float(text) if kind == "float" else int(text)
            except ValueError:
                return
        s = (self._cur() or {}).get("summary") or {}
        for sec in (s.get("config") or {}).get("sections") or []:
            for it in _items(sec):
                if it.get("var") == var and it.get("value") == value:
                    return  # 변경 없음 (포커스 이동만)
        self._call("set_config", {"var": var, "value": value}, "설정 변경됨")

    def _render_skills(self, s: dict) -> None:
        """위쪽 '주 스킬' 선택 줄 (그룹 사용·Full DPS 체크는 '스킬 · 젬' 탭)."""
        import skillnames
        from overlay import SLOT_KO

        groups = s.get("groups") or []
        main = s.get("mainSocketGroup")
        ready = self.client.state == "ready"
        self.main_combo.clear()
        cur = 0
        for i, g in enumerate(groups, start=1):
            gems = [x for x in (g.get("gems") or []) if not x.get("support")]
            label = g.get("label") or ", ".join(x["name"] for x in gems)
            if not label or label.startswith("<No active"):
                continue
            off = "" if g.get("enabled", True) else "  (꺼짐)"
            slot = g.get("slot") or ""
            self.main_combo.addItem(f"{skillnames.group_label(label)}  ·  {SLOT_KO.get(slot, slot) or '아이템/기타'}{off}", i)
            self.main_combo.setItemData(self.main_combo.count() - 1, f"{label} · {slot}", Qt.ItemDataRole.ToolTipRole)
            if i == main:
                cur = self.main_combo.count() - 1
        self.main_combo.setCurrentIndex(cur)
        self.main_combo.setEnabled(ready and self.main_combo.count() > 0)
        mg = groups[main - 1] if isinstance(main, int) and 0 < main <= len(groups) else {}
        actives = mg.get("actives") or []
        self.active_combo.clear()
        asc = s.get("ascend") or None  # 바알 면죄 · 바알 지배: 바알 쪽 = 승천한 파수꾼
        for j, a in enumerate(actives):
            label = skillnames.skill_label(a)
            tip = a + ("\n바알 영혼을 모아 쓰는 스킬이에요" if skillnames.is_vaal(a) else "")
            if asc and j + 1 == asc.get("vaal"):
                label = f"{skillnames.ko(a)}  (승천한 파수꾼)"
                tip = a + "\n파수꾼을 승천시키는 바알 스킬이에요. 승천한 파수꾼 기준으로 계산해요 (떠 있는 20초 동안)"
            elif asc and j + 1 == asc.get("normal"):
                label = f"{skillnames.ko(a)}  (일반 파수꾼)"
                tip = a + "\n평소에 떠 있는 일반 파수꾼 기준으로 계산해요"
            self.active_combo.addItem(label)
            self.active_combo.setItemData(j, tip, Qt.ItemDataRole.ToolTipRole)
        cur_active = int(mg.get("mainActiveSkill") or 1)
        if asc:
            cur_active = asc["vaal"] if asc.get("on") else asc["normal"]
        self.active_combo.setCurrentIndex(cur_active - 1)
        self._skill_fields[self.active_combo].setVisible(len(actives) > 1)
        self.active_combo.setEnabled(ready)
        parts = s.get("skillParts") or []
        self.part_combo.clear()
        self.part_combo.addItems(parts)
        self.part_combo.setCurrentIndex(int(s.get("skillPart") or 1) - 1)
        self._skill_fields[self.part_combo].setVisible(len(parts) > 1)
        self.part_combo.setEnabled(ready)
        for cb, items, sel in ((self.minion_combo, s.get("minions") or [], s.get("minionSel")),
                               (self.minion_skill_combo, s.get("minionSkills") or [], s.get("minionSkillSel"))):
            cb.clear()
            for j, it in enumerate(items):
                cb.addItem(skillnames.ko(it))
                cb.setItemData(j, it, Qt.ItemDataRole.ToolTipRole)
            cb.setCurrentIndex(max(0, min(int(sel or 1), len(items)) - 1))
            self._skill_fields[cb].setVisible(len(items) > 0)
            cb.setEnabled(ready and len(items) > 1)
        if asc:  # 일반 / 승천 파수꾼은 '그룹 안의 스킬' 에서 고르니 소환수 칸은 숨김
            self._skill_fields[self.minion_combo].hide()
    # ================================================================ 조작
    def _set_main(self, i) -> None:
        c = self._cur()
        if c and isinstance(i, int) and i != ((c.get("summary") or {}).get("mainSocketGroup")):
            self.client.call("set_main_group", {"index": i}, lambda r: self._apply_result(c["id"], r, "주 스킬 변경됨"),
                             self._on_call_err)

    def _call(self, cmd: str, args: dict, msg: str) -> None:
        c = self._cur()
        if c and self.client.state == "ready":
            self._ensure_loaded()
            self.client.call(cmd, args, lambda r: self._apply_result(c["id"], r, msg), self._on_call_err)

    def _set_minion_in_main(self, on: bool) -> None:
        s = load_settings()
        s["minion_in_main"] = bool(on)
        save_settings(s)
        if self.client.state == "ready":
            self._call("set_minion_in_main", {"on": bool(on)},
                       "주 스킬 DPS에 소환수 포함" if on else "주 스킬 DPS에서 소환수 뺌")

    def _on_active_combo(self, i: int) -> None:
        s = (self._cur() or {}).get("summary") or {}
        asc = s.get("ascend")
        if asc and i + 1 in (asc.get("vaal"), asc.get("normal")):
            on = i + 1 == asc.get("vaal")
            self._call("set_ascend", {"on": on}, "승천한 파수꾼으로 계산" if on else "일반 파수꾼으로 계산")
            return
        if s.get("mainSocketGroup"):
            self._call("set_active_skill", {"group": s["mainSocketGroup"], "active": i + 1}, "액티브 스킬 변경됨")

    def copy_pob_code(self) -> None:
        c = self._cur()
        xml = self.store.xml(c["id"]) if c else ""
        if not xml:
            self.flash("복사할 빌드가 없습니다")
            return
        code = base64.urlsafe_b64encode(zlib.compress(xml.encode("utf-8"), 9)).decode("ascii")
        QApplication.clipboard().setText(code)
        self.flash("PoB 코드 복사됨 — PoB 에서 Import/Export Build → Import from code 에 붙여넣으세요")

    def _set_group(self, i: int, enabled=None, full_dps=None) -> None:
        c = self._cur()
        if c:
            self.client.call("set_group", {"index": i, "enabled": enabled, "full_dps": full_dps},
                             lambda r: self._apply_result(c["id"], r, "스킬 설정 변경됨"), self._on_call_err)

    def compare_for_overlay(self, text: str, ok, err, nodef: list | None = None) -> str | None:
        """오버레이용: 현재 캐릭터로 아이템 비교. 비교할 수 없으면 None, 시작했으면 캐릭터 이름."""
        c = self._cur()
        if c is None or self.client.state not in ("ready", "starting"):
            return None
        # 엔진이 시작 중이면 요청은 클라이언트 큐에서 대기했다가 초기화 후 처리된다
        if self.client.state == "ready":
            self._ensure_loaded()
        else:
            xml = self.store.xml(c["id"])
            if not xml:
                return None
            self.loaded_id = c["id"]
            self.client.call("load_xml", {"xml": xml, "name": c["name"]},
                             lambda r: self._apply_result(c["id"], r, record=False), self._on_call_err)
        self.client.call("compare", {"text": text, "nodef": list(nodef or [])}, ok, err)
        return c["name"]

    # ================================================================ 메뉴
    def fill_menu(self, m: QMenu) -> None:
        m.addAction("캐릭터 가져오기…\tCtrl+T", self.open_import)
        m.addAction("현재 캐릭터 다시 가져오기", self.refresh_char)
        m.addSeparator()
        up = getattr(self, "updater", None)
        if up is not None:
            m.addAction("PoB 엔진 업데이트 확인 (점검 후 적용)", lambda: up.check_pob(manual=True))
            m.addAction("PoB 이전 버전으로 되돌리기", up.rollback)
            m.addAction("번역 데이터 지금 갱신", lambda: up.update_dict(manual=True))
        else:
            m.addAction("PoB 엔진 업데이트 확인", lambda: self.install_engine(force_check=True))
        m.addAction("PoB 엔진 다시 시작", self.client.start)
