"""품목별 거래소 검색창의 기본 체크만 정한다."""

EQUIPMENT = "equipment"
AREA_LEVEL = "area_level"
GEM = "gem"
FLASK = "flask"
OTHER = "other"


def apply_defaults(info, stats, filters):
    if not info.supported:
        return
    if info.template == AREA_LEVEL:
        for name, check in filters.items():
            if check.isEnabled() and not check.isHidden():
                check.setChecked(name == "monster_level")
        for row, check in stats:
            if check.isEnabled():
                check.setChecked(row.kind == "heist_area")
    elif info.template and info.corrupted and not filters["corrupted"].isHidden():
        filters["corrupted"].setChecked(False)
