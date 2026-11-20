"""RePoE stat_translations를 지도 옵션의 정수 롤 문구로 렌더링한다."""
from collections import defaultdict
from itertools import product

from build_map_mods import RANGE, clean


def roll_points(low, high, conditions=()):
    points = {low, high, -1, 0, 1}
    power = 10
    while power <= max(abs(low), abs(high)):
        points.update((power - 1, power, -power, 1 - power))
        power *= 10
    for condition in conditions:
        if "min" in condition:
            points.update((condition["min"] - 1, condition["min"]))
        if "max" in condition:
            points.update((condition["max"], condition["max"] + 1))
    return sorted(value for value in points if low <= value <= high)


def _apply_handlers(value, names, handlers):
    for name in names:
        handler = handlers[name]
        kind = handler["type"]
        if kind == "noop":
            continue
        if kind == "int":
            value = value * handler.get("multiplier", 1) / handler.get("divisor", 1)
            if "precision" in handler:
                value = round(value, handler["precision"])
        elif kind == "relational":
            value = handler["values"].get(str(int(value)), str(value))
        else:
            raise ValueError(f"지원하지 않는 RePoE 값 핸들러: {name}")
    return value


def _render_template(template, values, handlers):
    args = []
    for i, (value, fmt, names) in enumerate(zip(values, template["format"], template["index_handlers"])):
        if fmt == "ignore":
            args.append("")
            continue
        if fmt not in ("#", "+#"):
            raise ValueError(f"지원하지 않는 RePoE 포맷 {i}: {fmt}")
        value = _apply_handlers(value, names, handlers)
        args.append(value if isinstance(value, str) else format(value, "+g" if fmt == "+#" else "g"))
    return clean(template["string"].format(*args))


def _matches(template, values):
    return all(c.get("min", value) <= value <= c.get("max", value)
               for c, value in zip(template["condition"], values))


def source_lines(mod):
    return tuple(clean(line) for line in (mod.get("text") or "").splitlines() if line.strip())


def _source_variants(line):
    ranges = tuple(RANGE.finditer(line))
    values = [roll_points(*sorted((int(match[1]), int(match[2]))))
              if all("." not in match[i] for i in (1, 2)) else (match[1], match[2])
              for match in ranges]
    for roll in product(*values):
        replacements = iter(roll)
        yield RANGE.sub(lambda _: str(next(replacements)), line)


class Renderer:
    def __init__(self, translations, locale, handlers):
        self.rows = defaultdict(list)
        self.handlers = handlers
        for row in translations:
            if variants := row.get(locale):
                group = (tuple(row["ids"]), variants)
                for stat_id in row["ids"]:
                    self.rows[stat_id].append(group)

    def render(self, mod, skeleton):
        source = source_lines(mod)
        source_skeletons = {skeleton(line) for line in source}
        ranges = {s["id"]: (s["min"], s["max"]) for s in mod["stats"]}
        groups, covered = [], set()
        for stat_id in ranges:
            for ids, templates in self.rows[stat_id]:
                if not covered.intersection(ids):
                    groups.append((ids, templates))
                    covered.update(ids)

        # 각 번역 그룹을 한 번 평가한다. 같은 그룹의 값은 함께 조합한다.
        projections, translated_skeletons = [], set()
        for ids, templates in groups:
            axes = [roll_points(*ranges.get(stat_id, (0, 0)), (t["condition"][i] for t in templates))
                    for i, stat_id in enumerate(ids)]
            strings, group_skeletons = set(), set()
            for values in product(*axes):
                template = next((t for t in templates if _matches(t, values)), None)
                text = _render_template(template, values, self.handlers) if template else ""
                lines = tuple(filter(None, text.splitlines()))
                strings.add(lines)
                group_skeletons.update(skeleton(line) for line in lines)
            # 루트 번역표에는 모드 원문에서 숨겨진 스탯의 문구도 있다.
            # 원본에 출력되는 그룹만 렌더하되 그 그룹의 다른 롤 문구는 모두 검사한다.
            if source_skeletons & group_skeletons:
                translated_skeletons.update(group_skeletons)
                projections.append(sorted(strings))

        # 루트 번역 export에 없는 지도 전용 줄(예: 보상 줄)도 원본에서 빠뜨리지 않는다.
        for line in source:
            if skeleton(line) not in translated_skeletons:
                projections.append([(text,) for text in _source_variants(line)])
        return tuple(sorted({tuple(dict.fromkeys(line for group in variant for line in group))
                             for variant in product(*projections)}))
