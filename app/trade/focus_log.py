"""거래소 창 포커스 진단. 호출 경로는 고정 범주만 전달한다."""
import json
from datetime import datetime, timezone

import paths

LOG_NAME = "trade-focus.log"
MAX_BYTES = 64 * 1024


def record(open_id: str, event: str, foreground: str, **details) -> None:
    line = (json.dumps({
        "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "open_id": open_id, "event": event, "foreground": foreground,
        "synthetic_alt": 0, **details,
    }, separators=(",", ":")) + "\n").encode("utf-8")
    path = paths.LOCAL / LOG_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab+") as output:
            if output.tell() + len(line) > MAX_BYTES:
                output.truncate(0)
            output.write(line)
    except OSError:
        pass  # 진단 파일을 쓸 수 없어도 창 동작은 계속한다.
