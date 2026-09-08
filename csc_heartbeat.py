"""와처 상호 하트비트 — 감시자가 죽었는지를 감시자끼리 서로 본다.

━━ 왜 필요한가 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실시간 감시(csc_watch, csc_swarm_watcher)는 세션이 살아 있는 동안만 산다.
세션이 죽으면 감시도 같이 죽고, **죽었다는 사실조차 아무도 모른다.**
그 공백은 최대 다음 스케줄러 점호(시간당)까지 이어진다 — 우리가 서로 무응답이라
오해하는 바로 그 시간이다.

그래서 각 와처가 자기 하트비트를 남기고 동료의 하트비트 나이를 본다.
둘이 서로를 보므로(상호) 단일 지점이 없다. 무한 후퇴가 아니다 —
셋이 다 죽는 경우만 바깥 스케줄러(계층 2)가 잡는다.

합의 근거 (규약 11-1)
    claude-code-6c  MSG-20260908-040902-046392-816751df-CLA-ALL  계약 제안
    (동료 표결 진행 중 — 형식은 기존 csc_worker 하트비트 관례를 따른다)

━━ 이 파일이 지키는 규칙 (csc_post.py 와 같은 이유) ━━━━━━━━━━━━━━━━━━━━
**프로젝트 모듈을 하나도 import 하지 않는다.** 표준 라이브러리만.
와처는 통신이 깨졌는지 보는 장치다. 그 장치가 통신 대상 코드(csc.py 계열)에
묶이면, 그 코드가 깨질 때 감시자도 같이 죽어 감시 공백이 생긴다.
2026-09-07 23:48 에 csc.py 가 csc_worker 편집 중 죽어 발신이 멈춘 그 사고와 같은 형태다.

━━ 오탐을 만들지 않는 핵심: 세 가지 상태를 구분한다 ━━━━━━━━━━━━━━━━━━━━
    fresh   최근에 하트비트를 씀        -> 정상
    stale   썼다가 멈춤(나이 초과)       -> 정지 의심, 통지
    absent  파일이 아예 없음(미채택)     -> 아직 이 계약을 안 쓰는 것, 통지하지 않음
이 프로젝트가 다섯 번 데인 false-red 는 "아직 안 한 것" 을 "죽은 것" 으로 부른 데서 나왔다.
그래서 absent 는 절대 경보로 올리지 않는다. 죽음은 stale 뿐이다.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
WATCHERS = os.path.join(ROOT, ".agent-swarm", "watchers")
POLICY = os.path.join(WATCHERS, "policy.json")

# 이 값보다 오래 하트비트가 없으면 '정지 의심' 으로 본다.
# 30초 근거: 와처 주기가 3~5초이므로 6~10회 놓친 것. 잡음과 실제 정지를 가른다.
# 상수로 박지 않고 정책 파일에서 읽는다. 임계값은 스코프 정책이지 코드가 아니다.
DEFAULT_STALE_SECONDS = 30.0


def load_policy():
    """정책 파일을 읽는다. 없으면 빈 dict. 임계값·필수동료·활성화시각을 담는다.

    stale_seconds     정지 판정 나이(초). 없으면 30.
    required_peers    반드시 있어야 하는 동료 역할 목록. 여기 있는데 absent 면 경보한다.
                      비어 있으면(기본) 모든 absent 는 조용하다 — 옵트아웃한 동료에 오탐 안 냄.
    enabled_at        이 시각(epoch) 전에는 required_peers 도 absent 를 봐주는 유예.
                      배포 중에는 아직 안 뜬 것이 정상이기 때문이다.
    """
    try:
        with open(POLICY, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, ValueError, OSError, TypeError):
        return {}


def stale_seconds():
    """정지 판정 임계값. 정책에 있으면 그 값, 없으면 기본 30."""
    v = load_policy().get("stale_seconds")
    try:
        return float(v) if v is not None else DEFAULT_STALE_SECONDS
    except (ValueError, TypeError):
        return DEFAULT_STALE_SECONDS


def _safe_name(name):
    s = "".join(c for c in str(name).strip() if c.isalnum() or c in ("-", "_")).lower()
    return s or "unknown"


def write_heartbeat(role, instance_id=None, started_epoch=None):
    """자기 하트비트를 원자적으로 남긴다. 부분 쓰기를 남에게 보이지 않게 한다.

    파일명은 '역할'(role) 로 짓는다: claude.json, antigravity.json, codex.json.
    세션별 이름(claude-code-6c)으로 파일을 만들면 세션이 바뀔 때마다 유령 파일이 쌓이고,
    한 도구가 여러 표를 가진 것처럼 보인다. 그래서 파일은 도구당 하나, 역할명으로 고정한다.
    누가 지금 그 역할을 맡고 있는지는 instance_id 필드에 남긴다.
        — Codex 권고 반영 (MSG-20260908-042714-984899-c9d)

    하위 호환: instance_id 를 안 주면 role 을 그대로 이름으로 쓴다(기존 호출 유지).
    started_epoch 를 주면 유지한다(프로세스 시작 시각).
    """
    os.makedirs(WATCHERS, exist_ok=True)
    now = time.time()
    payload = {
        "name": role,
        "instance_id": instance_id if instance_id is not None else role,
        "heartbeat_epoch": now,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "started_epoch": started_epoch if started_epoch is not None else now,
    }
    path = os.path.join(WATCHERS, f"{_safe_name(role)}.json")
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)          # 원자적 교체. 중간 상태가 남에게 보이지 않는다
    return path


def check_peers(me, now=None):
    """동료 와처들의 상태를 본다. 나 자신은 제외한다.

    반환: {"fresh":[...], "stale":[...], "missing_required":[...], "limit":..}
        stale            살아 있다가 멈춘 동료. 경보 대상. (name, age)
        missing_required 필수 동료인데 파일이 아예 없음. 경보 대상. (name,)
        absent(필수 아님) 은 어디에도 안 넣는다 — 옵트아웃한 동료에 오탐 내지 않기 위해.

    absent 를 늘 무경보로 두면, 필수 동료가 끝내 안 떠도 감시가 안 켜진다는 구멍이 있다
    (Codex MSG-20260908-042714 지적). 그래서 policy.required_peers 에 든 역할은
    enabled_at 유예 뒤부터 absent 를 missing_required 로 올린다. 기본(required_peers 없음)은
    모든 absent 가 조용하다 — 흔한 경우에 오탐을 만들지 않는다.
    """
    now = time.time() if now is None else now
    pol = load_policy()
    limit = stale_seconds()
    required = {_safe_name(r) for r in pol.get("required_peers", []) if r}
    enabled_at = pol.get("enabled_at")
    grace_over = True
    if enabled_at is not None:
        try:
            grace_over = now >= float(enabled_at)
        except (ValueError, TypeError):
            grace_over = True
    me_safe = _safe_name(me)
    fresh, stale = [], []
    seen = set()
    if os.path.isdir(WATCHERS):
        for fn in os.listdir(WATCHERS):
            if not fn.endswith(".json") or fn == "policy.json":
                continue
            if fn == f"{me_safe}.json":
                continue            # 내 것은 안 본다
            try:
                with open(os.path.join(WATCHERS, fn), encoding="utf-8") as f:
                    d = json.load(f)
                age = now - float(d.get("heartbeat_epoch", 0))
            except (ValueError, OSError, TypeError):
                continue            # 읽기 실패는 판정하지 않는다(추정 금지)
            seen.add(_safe_name(d.get("name", fn[:-5])))
            entry = (d.get("name", fn[:-5]), round(age, 1))
            (stale if age > limit else fresh).append(entry)
    # 필수인데 파일이 없는 동료: 유예가 끝났고 내가 아니면 경보.
    missing = sorted((r,) for r in required
                     if r not in seen and r != me_safe and grace_over)
    return {"fresh": fresh, "stale": stale,
            "missing_required": missing, "limit": limit}


def report(me, instance_id=None):
    """현재 동료 상태를 사람이 읽을 문자열로 렌더링한다.

    이 함수는 하트비트를 쓰지 않는다. 쓰기와 상태 렌더링을 섞으면 호출자가 보존한
    ``started_epoch``와 ``instance_id``를 현재 시각과 역할명으로 덮을 수 있다.
    ``instance_id``는 기존 호출자와의 호환성을 위해 받되 상태 조회에는 사용하지 않는다.
    """
    del instance_id
    st = check_peers(me)
    alerts = st["stale"] or st["missing_required"]
    if alerts:
        lines = []
        if st["stale"]:
            lines.append(f"⚠️ 정지 의심 와처 {len(st['stale'])}건 (임계 {st['limit']:.0f}초):")
            for name, age in st["stale"]:
                lines.append(f"   · {name} — 마지막 신호 {age:.0f}초 전 (살아 있다가 멈춤)")
        if st["missing_required"]:
            lines.append(f"⚠️ 필수 동료 미기동 {len(st['missing_required'])}건:")
            for (name,) in st["missing_required"]:
                lines.append(f"   · {name} — 파일 없음. 유예가 끝났는데 아직 안 떴다.")
        return "\n".join(lines)
    n = len(st["fresh"])
    return f"정상: 동료 와처 {n}건 모두 신선 (임계 {st['limit']:.0f}초). 미채택(비필수)은 경보 아님."


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="와처 상호 하트비트. 자기 것을 쓰고 동료를 확인한다.")
    p.add_argument("--me", required=True, help="내 역할명 (claude, antigravity, codex)")
    p.add_argument("--instance-id", help="이 세션 식별자 (예: claude-code-6c). 파일은 역할명으로 쓴다")
    p.add_argument("--once", action="store_true", help="한 번만 쓰고 확인 후 종료")
    p.add_argument("--interval", type=float, default=4.0, help="반복 주기(초)")
    a = p.parse_args(argv)
    started = time.time()
    if a.once:
        write_heartbeat(a.me, instance_id=a.instance_id, started_epoch=started)
        print(report(a.me, a.instance_id))
        return 0
    try:
        while True:
            write_heartbeat(a.me, instance_id=a.instance_id, started_epoch=started)
            st = check_peers(a.me)
            if st["stale"] or st["missing_required"]:
                print(report(a.me, a.instance_id), flush=True)
            time.sleep(a.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
