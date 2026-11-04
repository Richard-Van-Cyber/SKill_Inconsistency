#!/usr/bin/env python3
"""Simulate the in-container privilege edge for the packs-resolve-exit-contract verifier.

The authoring host cannot be root, so this script patches exactly the two platform edges
(`SANDBOX`/`DROP_PREFIX` and the readability probe) to what they are inside the container, then
runs the real verifier unmodified over a real fixture. It answers two questions the local gate
cannot:

  A. root + a sandbox user (`agent`): the suite must score the oracle 11/11, i.e. dropping to the
     sandbox uid makes mode 0000 a real denial while root itself would have bypassed it.
  B. root + no sandbox user: the unreadable-layer assertions must refuse loudly (never score a
     condition that never held) instead of silently passing.

Usage: python3 experiments/wildskills25-20261001/probe_root_path.py <oracle-workspace> <logs>
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
VERIFIER = REPO / "wildskills" / "dynamic_eval" / "tasks" / "packs-resolve-exit-contract" / "verifier" / "verify_packs_resolve_exit_contract.py"


class FakeUser:
    pw_name = "agent"
    pw_uid = 4242
    pw_gid = 4242


def load():
    spec = importlib.util.spec_from_file_location("v", VERIFIER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(mod, root_like: bool, sandbox: bool):
    mod.SANDBOX = FakeUser() if sandbox else None
    mod.DROP_PREFIX = ["runuser", "-u", "agent", "--"] if sandbox else []
    results = mod.run_checks()
    return {name: (ok, detail) for name, ok, detail in results}


def main() -> int:
    workspace, logs = sys.argv[1], sys.argv[2]
    os.environ["WST25_WORKSPACE"] = workspace
    os.environ["WST25_LOGS"] = logs

    # --- A: as root, with the sandbox user available -----------------------------------------
    # Patch the privilege edge only. The sandbox uid is modelled by *what that uid can read* (mode
    # 0000 -> denied) and by the command `as_sandbox` builds; the fixture, the lock, the delivered
    # resolver and every check stay the real ones.
    mod = load()
    mod.TMP_ROOT = Path(__import__("tempfile").mkdtemp(prefix="wst25-rootprobe-"))
    mod.SANDBOX = FakeUser()
    mod.DROP_PREFIX = []
    real_as_sandbox = mod.as_sandbox
    seen = {"argv": [], "views": [], "env": {}}
    real_child_view = mod.child_view

    def spy_child_view(repo, layer, cache_root=None):
        view = real_child_view(repo, layer, cache_root)
        view["locked"] = (os.stat(layer).st_mode & 0o777) == 0
        seen["views"].append(view)
        if not seen["env"]:
            seen["env"] = mod.child_env(cache_root)
        return view

    mod.child_view = spy_child_view

    def wrapped_as_sandbox(argv):
        seen["argv"].append(real_as_sandbox(list(argv)))
        return list(argv)          # this host cannot drop; run the child as ourselves

    def probe_as_sandbox(path):
        seen["argv"].append(real_as_sandbox([sys.executable, "-c", "<probe>", str(path)]))
        return (os.stat(path).st_mode & 0o777) != 0, "agent (simulated)"

    mod.as_sandbox = wrapped_as_sandbox
    mod.child_can_read = probe_as_sandbox
    mod.RESOLVER = mod.find_resolver()
    res_a = run(mod, root_like=True, sandbox=True)
    npass = sum(1 for ok, _ in res_a.values() if ok)
    problems = []
    if not all(v["repo_seen"] for v in seen["views"]):
        problems.append("a child view did not discover the fixture repository")
    if not all(v["readable"] is False for v in seen["views"] if v["locked"]):
        problems.append("a locked layer was readable to the child")
    if not all(v["cwd"] and str(v["cwd"]).endswith("heldout-monorepo") for v in seen["views"]):
        problems.append("the child's cwd is not the fixture repo root")
    if seen["env"].get("GIT_CONFIG_KEY_0") != "safe.directory":
        problems.append("safe.directory is not exported to the child's git")
    print(f"   child views: {len(seen['views'])} probes, "
          f"cwd/uid recorded={[ (v['cwd'], v['uid']) for v in seen['views'][:1] ]}")
    print(f"   child git env: GIT_CONFIG_KEY_0={seen['env'].get('GIT_CONFIG_KEY_0')!r} "
          f"GIT_CONFIG_VALUE_0={seen['env'].get('GIT_CONFIG_VALUE_0')!r}")
    print("   traversal status of the fixture tree (dirs must be searchable by the child):",
          "OK" if not problems else problems)
    print(f"A. root verifier + sandbox user 'agent' (drop modelled, oracle delivery): "
          f"{npass}/11 checks passed")
    for name, (ok, detail) in res_a.items():
        if not ok:
            print(f"   [FAIL] {name}: {detail[:130]}")
    print("   drop commands the verifier would execute:")
    for argv in seen["argv"][:2]:
        print("    ", argv)
    print("   -> root reads mode 0000 (CAP_DAC_OVERRIDE); the dropped child is what makes the")
    print("      lock real, and the suite scores the delivery through that child.")

    # --- B: as root, with no sandbox user ----------------------------------------------------
    mod2 = load()
    mod2.TMP_ROOT = Path(__import__("tempfile").mkdtemp(prefix="wst25-rootprobe2-"))
    mod2.RESOLVER = mod2.find_resolver()
    mod2.SANDBOX = None
    mod2.DROP_PREFIX = []
    real_geteuid = os.geteuid
    os.geteuid = lambda: 0                                  # pretend the verifier is root
    try:
        res_b = run(mod2, root_like=True, sandbox=False)
    finally:
        os.geteuid = real_geteuid
    lock_checks = [n for n in res_b if "unreadable" in n or "locked" in n or "prefix" in n]
    refused = [n for n in lock_checks if not res_b[n][0]]
    print(f"\nB. root verifier + no sandbox user: {sum(1 for ok, _ in res_b.values() if ok)}/11 "
          f"passed; {len(refused)}/{len(lock_checks)} lock-dependent checks refused to score")
    print("   sample detail:", res_b["unreadable_fixture_is_really_locked"][1][:200])

    # --- C: the v3-in-container failure mode, modelled ---------------------------------------
    # A dropped child that cannot traverse the fixture root answers `not inside a git repository`
    # and never reaches the config layer. Model exactly that (repo_seen=False plus the unsearchable
    # component) and check the assertion names it instead of scoring silently.
    mod3 = load()
    mod3.TMP_ROOT = Path(__import__("tempfile").mkdtemp(prefix="wst25-rootprobe3-"))
    mod3.SANDBOX = FakeUser()
    mod3.DROP_PREFIX = []
    mod3.RESOLVER = mod3.find_resolver()
    real_view3 = mod3.child_view

    def blind_child_view(repo, layer, cache_root=None):
        view = real_view3(repo, layer, cache_root)
        view.update(repo_seen=False, repo_detail="fatal: not a git repository",
                    unsearchable=[str(repo.parents[1])], readable=None)
        return view

    mod3.child_view = blind_child_view
    res_c = run(mod3, root_like=True, sandbox=True)
    detail = res_c["unreadable_fixture_is_really_locked"][1]
    names_cause = "not inside a git repository" in detail or "discover the fixture" in detail
    print(f"\nC. drop modelled as unable to traverse the fixture (the v3-in-container failure):")
    print(f"   unreadable_fixture_is_really_locked -> {'FAIL (as it must)' if not res_c['unreadable_fixture_is_really_locked'][0] else 'PASS (BAD)'}")
    print("   detail:", detail[:230])
    print("   assertion names the cause:", names_cause)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
