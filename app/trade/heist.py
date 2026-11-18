"""고정 APT client_strings의 강탈 속성과 거래소 필드."""
import re
from dataclasses import dataclass

CONTRACT = "Heist Contract"
BLUEPRINT = "Heist Blueprint"
CLASSES = {"Contracts": CONTRACT, "Heist Contracts": CONTRACT, "계약": CONTRACT,
           "Blueprints": BLUEPRINT, "Heist Blueprints": BLUEPRINT, "도면": BLUEPRINT}
CATEGORIES = {CONTRACT: "heistmission.contract", BLUEPRINT: "heistmission.blueprint"}
JOBS = (
    ("Lockpicking", "자물쇠 따기", "lockpicking"),
    ("Brute Force", "완력", "brute_force"),
    ("Perception", "통찰력", "perception"),
    ("Demolition", "파괴 공작", "demolition"),
    ("Counter-Thaumaturgy", "반-마석학", "counter_thaumaturgy"),
    ("Trap Disarmament", "덫 해제", "trap_disarmament"),
    ("Agility", "민첩함", "agility"),
    ("Deception", "기만", "deception"),
    ("Engineering", "공학", "engineering"),
)
JOB = {"en": r"Requires (.+) \(Level ([0-9]+)(?:\s*\(unmet\))?\)",
       "ko": r"(.+) 필요\(([0-9]+)(?:\s*\(unmet\))?레벨\)"}
TARGET = {"en": "Heist Target: ", "ko": "강탈 대상: "}
PRICELESS = {"en": "Priceless", "ko": "환산 불가능한 가치"}
WINGS = {"en": "Wings Revealed: ", "ko": "부속 건물 드러남: "}
AREA = {"en": "Area Level: ", "ko": "지역 레벨: "}
AREA_API_VERIFIED = frozenset({BLUEPRINT, CONTRACT})
# 2026-11-18 머성이 카카오 Standard 도면: 대저택 링크로 지역 레벨 83~83을 확인했다.
AREA_BROWSER_VERIFIED = frozenset({BLUEPRINT})


@dataclass(frozen=True)
class Heist:
    area: int | None = None
    job: str = ""
    job_text: str = ""
    job_level: int | None = None
    priceless: bool = False
    wings: tuple[int, int] | None = None


def _property(lines, prefix):
    values = [line.removeprefix(prefix) for line in lines if line.startswith(prefix)]
    return values[0] if len(values) == 1 else ""


def read(lines, lang, category):
    area_text = _property(lines, AREA[lang])
    area = int(area_text) if re.fullmatch(r"[1-9][0-9]*", area_text) else None
    if category == CONTRACT:
        matches = [(line, m) for line in lines if (m := re.fullmatch(JOB[lang], line))]
        job, text, level = "", "", None
        if len(matches) == 1:
            text, match = matches[0]
            job = next((key for en, ko, key in JOBS if match[1] == (ko if lang == "ko" else en)), "")
            level = int(match[2])
        target = _property(lines, TARGET[lang])
        return Heist(area, job, text, level, target.endswith(f" ({PRICELESS[lang]})"))
    wings = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", _property(lines, WINGS[lang]))
    counts = tuple(map(int, wings.groups())) if wings else None
    return Heist(area, wings=counts if counts and counts[0] <= counts[1] else None)


def area_enabled(category):
    return category in AREA_API_VERIFIED and category in AREA_BROWSER_VERIFIED
