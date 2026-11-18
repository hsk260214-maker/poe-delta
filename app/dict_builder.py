"""(앱 내장 — tools/build_names.py 와 앱의 번역 데이터 자동 갱신이 함께 씀)
RePoE(영문/한글) 젬·버프 데이터로 영문 → 한글 공식 명칭 사전을 만든다.

출력: data/names_ko.json  {"names": {"Onslaught": "맹공", "Herald of Ash": "재의 전령", ...}}
PoB Configuration 의 스킬 소제목·용어 번역에 쓴다.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / ".cache"
OUT_DIR = ROOT / "data"  # 앱에서 자동 갱신할 때는 바꿔서 씀
BASE = "https://repoe-fork.github.io/"
FILES = ["gems.min.json", "Korean/gems.min.json", "buffs.min.json", "Korean/buffs.min.json"]


CHANGED: list[str] = []  # 이번 실행에서 실제로 새로 받은 파일


def download(url: str, path: Path, refresh: bool) -> None:
    """refresh 면 ETag 로 바뀐 경우만 다시 받는다 (304 면 캐시 유지)."""
    import urllib.error

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not refresh:
        return
    tag_file = path.with_name(path.name + ".etag")
    headers = {"User-Agent": "ExileDelta-data/1.0"}
    if path.exists() and tag_file.exists():
        headers["If-None-Match"] = tag_file.read_text(encoding="utf-8").strip()
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
            etag = r.headers.get("ETag")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return
        raise
    print("download", url)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    if etag:
        tag_file.write_text(etag, encoding="utf-8")
    CHANGED.append(path.name)


def fetch(name: str, refresh: bool) -> dict:
    path = CACHE / name.replace("/", "_")
    download(BASE + name, path, refresh)
    return json.loads(path.read_text(encoding="utf-8"))


def dig(obj, *path):
    for p in path:
        obj = obj.get(p) if isinstance(obj, dict) else None
    return obj


def main(refresh: bool | None = None) -> None:
    if refresh is None:
        refresh = "--refresh" in sys.argv
    ge, gk, be, bk = (fetch(n, refresh) for n in FILES)
    names: dict[str, str] = {}
    for key, g in ge.items():
        kg = gk.get(key) or {}
        for path in (("active_skill", "display_name"), ("base_item", "display_name")):
            a, b = dig(g, *path), dig(kg, *path)
            if a and b and a != b and not a.startswith("[DNT"):
                names.setdefault(a, b)
    for key, b in be.items():
        kb = bk.get(key) or {}
        if b.get("name") and kb.get("name") and b["name"] != kb["name"]:
            names.setdefault(b["name"], kb["name"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "names_ko.json").write_text(json.dumps({"names": names}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"names_ko.json: {len(names)} names")
    build_ko_en(refresh)


PH_RE = re.compile(r"\{(\d+)\}")


def _template(entry: dict) -> str | None:
    """stat 번역 한 줄 → '{0}' 자리에 표시 형식(+# 등)을 반영한 템플릿. 예: '+{0} to maximum Life'."""
    s = entry.get("string")
    if not s:
        return None
    fmts = entry.get("format") or []

    def rep(m):
        i = int(m.group(1))
        f = fmts[i] if i < len(fmts) else "#"
        if f == "ignore":
            return ""
        return f.replace("#", "{%d}" % i)

    return PH_RE.sub(rep, s)


def build_ko_en(refresh: bool) -> None:
    """한글 클라이언트 아이템 텍스트 → 영문 변환용 사전 (PoB 는 영문만 해석).

    stats: [한글 템플릿, 영문 템플릿]  ('{i}' 가 수치 자리, 같은 stat id·같은 조건 변형끼리 짝)
    bases: 한글 베이스 이름 → 영문,  classes: 한글 아이템 종류 → 영문
    """
    st_en = fetch("stat_translations.min.json", refresh)
    st_ko = fetch("Korean/stat_translations.min.json", refresh)
    ko_by_ids = {tuple(x["ids"]): x for x in st_ko}
    cands: dict[str, list[str]] = {}
    # 1순위: 게임 공식 stat 번역(같은 stat id 짝). 2순위(빈 곳 보충): APT 한글 매처 (클라이언트 표기 차이 보완)
    for x in st_en:
        k = ko_by_ids.get(tuple(x["ids"]))
        if not k:
            continue
        for a, b in zip(x.get("English") or [], k.get("Korean") or []):
            te, tk = _template(a), _template(b)
            if not te or not tk or te == tk:
                continue
            el, kl = te.split("\n"), tk.split("\n")
            if len(kl) > 1:
                # 여러 줄 옵션은 통째로도 등록 (한·영 줄바꿈 위치가 달라도 번역되도록; 영문도 게임 표기처럼 여러 줄)
                cands.setdefault("\n".join(x.strip() for x in kl), []).append("\n".join(x.strip() for x in el))
            if len(el) != len(kl):
                continue
            for e1, k1 in zip(el, kl):
                # 줄마다 수치 자리 개수가 같아야 (한·영 줄바꿈 위치가 다르면 엉뚱한 짝이 됨)
                if k1.strip() and e1.strip() and len(PH_RE.findall(k1)) == len(PH_RE.findall(e1)):
                    cands.setdefault(k1.strip(), []).append(e1.strip())
    n_apt = apt_stat_pairs(refresh, cands)
    # 같은 한글 문장이 여러 영문 stat 에 대응하면, 실제 아이템 옵션 문장에 나오는 영문을 우선
    mod_skel = set()
    for m in fetch("mods.min.json", refresh).values():
        if m.get("domain") in ("item", "crafted", "abyss_jewel", "misc") and m.get("text"):
            for ln in m["text"].split("\n"):
                mod_skel.add(_skel(ln))
    pairs: dict[str, str] = {}
    for k, lst in cands.items():
        pairs[k] = next((e for e in lst if _skel(e) in mod_skel), lst[0])
    b_en = fetch("base_items.min.json", refresh)
    b_ko = fetch("Korean/base_items.min.json", refresh)
    bases: dict[str, str] = {}
    uniques: dict[str, str] = {}
    for x in apt_ndjson("ko/items.ndjson", refresh):
        if x.get("name") and x.get("refName") and x["name"] != x["refName"]:
            if x.get("namespace") == "ITEM":
                bases.setdefault(x["name"], x["refName"])
            elif x.get("namespace") == "UNIQUE":
                uniques.setdefault(x["name"], x["refName"])
    for key, b in b_en.items():
        kb = b_ko.get(key) or {}
        if b.get("name") and kb.get("name") and b.get("release_state") != "unreleased":
            bases.setdefault(kb["name"], b["name"])
    c_en = fetch("item_classes.min.json", refresh)
    c_ko = fetch("Korean/item_classes.min.json", refresh)
    classes = {}
    for key, c in c_en.items():
        kc = c_ko.get(key) or {}
        if c.get("name") and kc.get("name"):
            classes.setdefault(kc["name"], c["name"])
    out = OUT_DIR / "ko_en.json"
    # 번역기는 골격이 같은 후보를 순서대로 시도 → 실제 아이템 옵션 문장을 앞에
    stats = sorted(pairs.items(), key=lambda kv: _skel(kv[1]) not in mod_skel)
    # implicit 종류 구분: 영문 문장 골격 → exarch(작열의 총주교) / eater(세계 포식자) / corrupted(바알 타락)
    gen_kind = {"searing_exarch_implicit": "exarch", "eater_of_worlds_implicit": "eater", "corrupted": "corrupted"}
    implicit_kinds: dict[str, list[str]] = {}
    for m in fetch("mods.min.json", refresh).values():
        k = gen_kind.get(m.get("generation_type"))
        if k and m.get("domain") == "item" and m.get("text"):
            for ln in m["text"].split("\n"):
                lst = implicit_kinds.setdefault(_skel(ln), [])
                if k not in lst:
                    lst.append(k)
    # 베이스 고유 implicit (예: 자수정 반지 = 카오스 저항) — 타락/엘드리치 implicit 과 구분용
    mods_all = fetch("mods.min.json", refresh)
    base_implicits: dict[str, list[str]] = {}
    for b in b_en.values():
        if b.get("name") and b.get("implicits") and b.get("domain") == "item":
            sk = []
            for mid in b["implicits"]:
                for ln in (mods_all.get(mid, {}).get("text") or "").split("\n"):
                    if ln.strip():
                        sk.append(_skel(ln))
            if sk:
                base_implicits.setdefault(b["name"], sk)
    # 옵션 문장 골격 → 옵션 태그 (촉매 특수 퀄리티 적용 여부 판단; PoB getCatalystScalar 와 같은 태그)
    mod_tags: dict[str, list[str]] = {}
    for m in mods_all.values():
        if m.get("domain") in ("item", "crafted", "abyss_jewel", "misc") and m.get("text") and m.get("implicit_tags"):
            # 통째(여러 줄 한 옵션) + 줄마다(하이브리드 옵션은 아이템에서 줄이 따로 나옴)
            t = m["text"]
            for sk in {_skel(t)} | {_skel(ln) for ln in t.split("\n") if ln.strip()}:
                lst = mod_tags.setdefault(sk, [])
                for tg in m["implicit_tags"]:
                    if tg not in lst:
                        lst.append(tg)
    # 아이템 종류별 태그 (PoB 의 타락/엘드리치 implicit weightKey 와 맞춰 장착 가능 여부 판단)
    class_tags: dict[str, list[str]] = {}
    for b in b_en.values():
        if b.get("domain") == "item" and b.get("release_state") == "released" and b.get("item_class"):
            s = set(class_tags.get(b["item_class"], []))
            s.update(b.get("tags") or [])
            class_tags[b["item_class"]] = sorted(s)
    # 패시브 트리 노드 효과 (영문 → 한글 표시 전용; 아이템 한→영 번역에는 쓰지 않음)
    passive: dict[str, str] = {}
    for f_en, f_ko in (("stat_translations/passive_skill.min.json", "Korean/stat_translations/passive_skill.min.json"),
                       ("stat_translations.min.json", "Korean/stat_translations.min.json")):
        p_ko = {tuple(x["ids"]): x for x in fetch(f_ko, refresh)}
        for x in fetch(f_en, refresh):
            k = p_ko.get(tuple(x["ids"]))
            if not k:
                continue
            for a, b in zip(x.get("English") or [], k.get("Korean") or []):
                te, tk = _template(a), _template(b)
                if not te or not tk or te == tk:
                    continue
                passive.setdefault("\n".join(s.strip() for s in te.split("\n")),
                                   "\n".join(s.strip() for s in tk.split("\n")))
                el, kl = te.split("\n"), tk.split("\n")
                if len(el) == len(kl) > 1:
                    for e1, k1 in zip(el, kl):
                        if e1.strip() and k1.strip() and len(PH_RE.findall(k1)) == len(PH_RE.findall(e1)):
                            passive.setdefault(e1.strip(), k1.strip())
    out.write_text(json.dumps({"stats": stats, "bases": bases, "uniques": uniques, "classes": classes,
                               "implicit_kinds": implicit_kinds, "base_implicits": base_implicits,
                               "class_tags": class_tags, "mod_tags": mod_tags,
                               "passive": sorted(passive.items())},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"ko_en.json: {len(pairs)} stat lines (APT {n_apt}), {len(bases)} bases, {len(uniques)} uniques, "
          f"{len(classes)} classes ({out.stat().st_size / 1024:.0f} KB)")


APT = "https://raw.githubusercontent.com/SnosMe/awakened-poe-trade/master/renderer/public/data/"


def apt_ndjson(path: str, refresh: bool, base: str = APT, flatten: bool = True) -> list[dict]:
    """Awakened PoE Trade (MIT) 데이터. 묶음 줄({"stats": [...]}) 은 펼친다."""
    import hashlib

    prefix = "" if base == APT else hashlib.sha256(base.encode("utf-8")).hexdigest()[:16] + "_"
    cp = CACHE / ("apt_" + prefix + path.replace("/", "_"))
    download(base + path, cp, refresh)
    out = []
    for line in cp.read_text(encoding="utf-8").splitlines():
        if line.strip():
            x = json.loads(line)
            out.extend(x["stats"] if flatten and "stats" in x else [x])
    return out


def _hash_tpl(s: str) -> str:
    """APT 매처의 '#' 를 순서대로 {0},{1}.. 로."""
    n = iter(range(100))
    return re.sub("#", lambda _: "{%d}" % next(n), s)


_RANGE = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*\)")
_NUM = re.compile(r"[+-]?\d+(?:\.\d+)?")


def _skel(s: str) -> str:
    """비교용 골격: 범위·숫자·자리표시를 모두 '#' 로, 부호 제거."""
    s = PH_RE.sub("#", s)
    s = _RANGE.sub("#", s)
    s = _NUM.sub("#", s)
    return re.sub(r"[+-]#", "#", s).strip().lower()


def apt_stat_pairs(refresh: bool, pairs: dict[str, list[str]]) -> int:
    ko = apt_ndjson("ko/stats.ndjson", refresh)
    en_by_ref: dict[str, dict] = {}
    for x in apt_ndjson("en/stats.ndjson", refresh):
        en_by_ref.setdefault(x["ref"], x)
    n = 0
    for x in ko:
        e = en_by_ref.get(x["ref"])
        if not e:
            continue
        em = e["matchers"]
        for i, m in enumerate(x["matchers"]):
            # 같은 위치·같은 성격(negate/value/advanced)의 영문 매처와 짝
            cand = [y for y in em if bool(y.get("negate")) == bool(m.get("negate"))
                    and y.get("value") == m.get("value") and bool(y.get("advanced")) == bool(m.get("advanced"))]
            target = em[i] if i < len(em) and em[i] in cand else (cand[0] if cand else None)
            if not target:
                continue
            kl, el = m["string"].split("\n"), target["string"].split("\n")
            if len(kl) > 1 and m["string"].count("#") == target["string"].count("#"):
                kj = _hash_tpl("\n".join(x.strip() for x in kl))
                ej = _hash_tpl("\n".join(x.strip() for x in el))
                lst = pairs.setdefault(kj, [])
                if ej not in lst:
                    lst.append(ej)
                    n += 1
            if len(kl) != len(el) or kl[0].count("#") != el[0].count("#"):
                continue
            for k1, e1 in zip(kl, el):
                k1, e1 = k1.strip(), e1.strip()
                if k1 and e1 and k1.count("#") == e1.count("#"):
                    lst = pairs.setdefault(_hash_tpl(k1), [])
                    if _hash_tpl(e1) not in lst:
                        lst.append(_hash_tpl(e1))
                        n += 1
    return n


if __name__ == "__main__":
    main()
