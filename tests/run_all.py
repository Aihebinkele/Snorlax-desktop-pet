"""轻量测试运行器：无需 pytest，直接收集并运行 tests/ 下所有 test_* 函数。

用法： python tests/run_all.py
"""
import importlib
import os
import sys
import traceback

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    mod_names = sorted(
        f[:-3] for f in os.listdir(TESTS_DIR)
        if f.startswith("test_") and f.endswith(".py") and f != "run_all.py"
    )

    total = 0
    passed = 0
    failures = []

    for mod_name in mod_names:
        mod = importlib.import_module(mod_name)
        funcs = [
            getattr(mod, name) for name in sorted(dir(mod))
            if name.startswith("test_") and callable(getattr(mod, name))
        ]
        for fn in funcs:
            total += 1
            label = f"{mod_name}::{fn.__name__}"
            try:
                fn()
                passed += 1
                print(f"  PASS  {label}")
            except Exception as exc:
                failures.append((label, exc))
                print(f"  FAIL  {label}")
                traceback.print_exc()

    print()
    print(f"结果：{passed}/{total} 通过")
    if failures:
        print("失败用例：")
        for label, exc in failures:
            print(f"  - {label}: {exc}")
        sys.exit(1)
    else:
        print("全部通过 ✅")


if __name__ == "__main__":
    main()
