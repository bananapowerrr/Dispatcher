# -*- coding: utf-8 -*-
def test_benchmark_offline_pass_rate():
    import scripts.benchmark_harness as bh
    # run main logic without writing file
    import tempfile
    from pathlib import Path
    results = []
    with tempfile.TemporaryDirectory(prefix="ab_bench_") as td:
        tmp = Path(td)
        for case in bh.CASES:
            k = case["kind"]
            if k in ("static_ok", "static_fail", "syntax_fail"):
                results.append(bh.run_static_case(tmp, case))
            elif k == "skill_match":
                results.append(bh.run_skill_case(case))
            elif k == "verify_policy":
                results.append(bh.run_verify_policy_case(case))
            elif k == "false_done":
                results.append(bh.run_false_done_case(case))
            elif k == "recipe":
                results.append(bh.run_recipe_case(case))
        results.append(bh.run_bus_cycle(tmp))
    passed = sum(1 for r in results if r.get("passed"))
    assert passed >= int(0.7 * len(results)), (passed, len(results), results)
