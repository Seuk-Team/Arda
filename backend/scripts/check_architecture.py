"""헥사고날 적용 상태 대조 — ADR-0035 가 정한 구조와 실제 코드를 맞춰 본다.

**왜 스크립트로 굳히나**: "포트·어댑터로 바꿨다" 는 말은 폴더를 만든 것만으로도
참이 되어 버린다. 실제로 이득(교체 가능성·DB 없는 테스트)이 나오는지는 **숫자로만**
보인다 — 포트를 주입받는 함수가 몇 개인지, 포트를 지나치는 원시 DB 접근이 몇 곳인지.
2026-09-12 감사에서 이 수치를 처음 재 봤고, 그때 "구조는 갖췄지만 실질은 절반" 이라는
판정이 나왔다. 손으로 세면 다음 달에 아무도 안 센다.

읽기만 한다 (AST 파싱). 코드도 DB 도 건드리지 않는다.

사용:
    python scripts/check_architecture.py            # 수치 출력
    python scripts/check_architecture.py --strict   # 기준선보다 나빠지면 종료 코드 1

`--strict` 의 기준선은 **2026-09-12 실측값**이다. 숫자를 줄이는 방향의 변경은 통과하고,
늘리는 변경(원시 DB 접근 추가·새 경계 위반)은 실패한다 — 기준선을 올리려면 그 이유를
커밋 메시지에 남기고 이 파일의 BASELINE 을 함께 고쳐라.
"""

from __future__ import annotations

import ast
import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / "app"
CONTEXTS = ("application", "interview", "hiring", "talent", "shared")

# 2026-09-12 실측. 늘어나면 --strict 가 실패한다.
BASELINE = {
    "adapter_module_level": 45,   # 도메인·라우터가 구체 어댑터를 모듈 레벨에서 import
    "raw_db_access": 143,         # 포트를 지나친 원시 DB 접근
    "boundary_crossings": 15,     # 컨텍스트 경계 넘김 (shared 경유 제외)
}


def rel(p: pathlib.Path) -> str:
    return p.relative_to(ROOT.parent).as_posix()


def layer(p: pathlib.Path) -> str:
    parts = p.relative_to(ROOT).parts
    if parts and parts[0] in CONTEXTS:
        return f"{parts[0]}/api" if "api" in parts else parts[0]
    return parts[0] if len(parts) > 1 else "app(root)"


def main() -> int:
    strict = "--strict" in sys.argv
    trees: dict[pathlib.Path, ast.Module] = {}
    for f in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        trees[f] = ast.parse(f.read_text(encoding="utf-8"))

    print(f"파일 {len(trees)}개\n")

    # ① 의존 방향 — 도메인이 구체 어댑터를 아는가
    module_level: list[str] = []
    deferred = 0
    for f, tree in trees.items():
        if f.relative_to(ROOT).parts[0] in ("adapter", "ports"):
            continue
        toplevel = {id(n) for n in tree.body}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            mod = getattr(node, "module", None) or ""
            names = " ".join(a.name for a in node.names)
            if not (mod.startswith("app.adapter") or "app.adapter" in names):
                continue
            if id(node) in toplevel:
                module_level.append(f"{rel(f)}:{node.lineno}")
            else:
                deferred += 1

    print(f"① 어댑터 직접 의존: 모듈 레벨 {len(module_level)} · 함수 내부 {deferred}")
    for k, v in collections.Counter(
        layer(ROOT.parent / w.split(":")[0]) for w in module_level
    ).most_common():
        print(f"     {k}: {v}")

    # ② 포트 미경유 원시 DB 접근
    raw = collections.Counter()
    total_raw = 0
    for f, tree in trees.items():
        if f.relative_to(ROOT).parts[0] == "adapter":
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("get", "scalar", "scalars", "execute", "query")
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "db"
            ):
                raw[layer(f)] += 1
                total_raw += 1

    print(f"\n② 포트 미경유 원시 DB 접근: {total_raw}")
    for k, v in raw.most_common(6):
        print(f"     {k}: {v}")

    # ③ 컨텍스트 경계 (shared 는 공용이라 제외)
    cross = collections.Counter()
    for f, tree in trees.items():
        parts = f.relative_to(ROOT).parts
        if not parts or parts[0] not in CONTEXTS:
            continue
        for node in ast.walk(tree):
            mod = node.module if isinstance(node, ast.ImportFrom) else None
            if not mod or not mod.startswith("app."):
                continue
            seg = mod.split(".")
            if len(seg) > 1 and seg[1] in CONTEXTS and seg[1] != parts[0]:
                if seg[1] == "shared":
                    continue  # 공용은 누구나 쓴다
                cross[(parts[0], seg[1])] += 1
    total_cross = sum(cross.values())
    print(f"\n③ 컨텍스트 경계 넘김 (shared 제외): {total_cross}")
    for (a, b), n in cross.most_common():
        note = "  ← 역방향 (공용이 특정 컨텍스트를 안다)" if a == "shared" else ""
        print(f"     {a} → {b}: {n}{note}")

    # ④ 포트 ↔ 어댑터 짝
    print("\n④ 포트 ↔ Pg 어댑터")
    pg_dir = ROOT / "adapter/outbound/pg"
    mismatch = 0
    for port in sorted((ROOT / "ports/output").glob("*_repository.py")):
        pm = {
            n.name
            for cls in ast.parse(port.read_text(encoding="utf-8")).body
            if isinstance(cls, ast.ClassDef)
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
        }
        impl = pg_dir / f"{port.stem.replace('_repository', '')}_pg_repository.py"
        if not impl.exists():
            print(f"     {port.name}: 구현 없음")
            mismatch += 1
            continue
        im = {
            n.name
            for cls in ast.parse(impl.read_text(encoding="utf-8")).body
            if isinstance(cls, ast.ClassDef)
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
        }
        missing = sorted(pm - im)
        print(f"     {port.name} ({len(pm)}) ↔ {impl.name}: {'일치' if not missing else f'미구현 {missing}'}")
        mismatch += bool(missing)

    # ⑤ 포트를 주입받는 함수 — 이 숫자가 곧 "실현된 이득"
    di: list[str] = []
    for f, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for arg in list(node.args.kwonlyargs) + list(node.args.args):
                ann = ast.unparse(arg.annotation) if arg.annotation else ""
                if "Repository" in ann or "Dispatcher" in ann:
                    di.append(f"{rel(f)}:{node.lineno} {node.name}")
                    break
    print(f"\n⑤ 포트를 주입받는 함수: {len(di)}")
    for d in di:
        print(f"     {d}")

    actual = {
        "adapter_module_level": len(module_level),
        "raw_db_access": total_raw,
        "boundary_crossings": total_cross,
    }
    print("\n기준선 대조 (2026-09-12 실측)")
    worse = []
    for k, base in BASELINE.items():
        now = actual[k]
        mark = "=" if now == base else ("↓ 개선" if now < base else "↑ 악화")
        print(f"     {k}: {now} (기준 {base}) {mark}")
        if now > base:
            worse.append(f"{k}: {base} → {now}")

    if mismatch:
        print("\n포트 ↔ 어댑터 불일치가 있다 — 부팅이 막히므로 먼저 고쳐라.")
    if worse and strict:
        print("\n기준선보다 나빠졌다:")
        for w in worse:
            print("  ", w)
        print("의도한 변경이면 이 파일의 BASELINE 을 같은 커밋에서 고쳐라.")
        return 1
    if mismatch and strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
