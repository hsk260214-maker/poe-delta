"""고정된 시범 파일에서 공개판의 시신 이름 검사용 지문만 생성한다."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT_SHA256 = "e13c9f0f5ffe2d3bf66336fdc237f82ec6475571fd38bc5cea6ae8e42e8b3a88"


def build(source: Path) -> bytes:
    pilot = json.loads(source.read_bytes())
    payload = json.dumps(pilot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if sha256(payload).hexdigest() != PILOT_SHA256:
        raise ValueError("승인된 시신 식별자 원본의 해시가 일치하지 않습니다")
    fingerprints = set()
    for namespace, _ref, name, category, discriminator, extra in pilot["corpse_items"]:
        if (namespace, category, discriminator, extra) != ("ITEM", "ItemisedCorpse", None, None):
            raise ValueError("지원하지 않는 시신 식별자 형식입니다")
        fingerprints.add(sha256(name.encode()).hexdigest())
    if len(fingerprints) != len(pilot["corpse_items"]):
        raise ValueError("동명 시신이 있습니다")
    return (json.dumps(sorted(fingerprints), indent=2) + "\n").encode()


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    args = parser.parse_args()
    output = build(args.pilot)
    (ROOT / "data" / "spectre_types.json").write_bytes(output)
    print(f"시신 지문 {len(json.loads(output))}개, SHA-256 {sha256(output).hexdigest()}")
