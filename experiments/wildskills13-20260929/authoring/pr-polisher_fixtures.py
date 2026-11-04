#!/usr/bin/env python3
"""Deterministic fixture builder for the `pr-polisher` task (wildskills13).

Run from the repo root:

    python3 experiments/wildskills13-20260929/authoring/pr-polisher_fixtures.py

It writes two kinds of artifacts, both byte-stable (fixed identities, fixed commit dates,
no network):

1. `<task>/environment/repo/` — the git repository the agent receives: a `main` baseline
   commit plus a `feature/user-service-polish` branch holding exactly one commit whose diff
   contains only WARNING-level issues.
2. `<task>/verifier/fixtures/*.tar` — four hidden git repositories the verifier unpacks into
   a scratch directory to exercise the agent's repaired `check_diff.py`.

The Nomulus-style anti-pattern regexes in the skill script are the ground truth for what
counts as ERROR vs WARNING; every fixture below is derived from the script's own rules and
was verified by running both the pristine and the repaired script over all four.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path('/workspace/skillEvaluation')
TASK = REPO / 'wildskills' / 'dynamic_eval' / 'tasks' / 'pr-polisher'
ENV_REPO = TASK / 'environment' / 'repo'
FIXTURES = TASK / 'verifier' / 'fixtures'

BASELINE_DATE = '2026-01-05T09:00:00+00:00'
FEATURE_DATE = '2026-01-06T10:30:00+00:00'

GIT_ENV = {
    'GIT_AUTHOR_NAME': 'Fixture Builder',
    'GIT_AUTHOR_EMAIL': 'fixture@example.com',
    'GIT_COMMITTER_NAME': 'Fixture Builder',
    'GIT_COMMITTER_EMAIL': 'fixture@example.com',
    'GIT_CONFIG_GLOBAL': '/dev/null',
    'GIT_CONFIG_SYSTEM': '/dev/null',
    'GIT_CONFIG_NOSYSTEM': '1',
}


def git(repo: Path, *args: str, date: str | None = None) -> str:
    env = dict(os.environ)
    env.update(GIT_ENV)
    if date:
        env['GIT_AUTHOR_DATE'] = date
        env['GIT_COMMITTER_DATE'] = date
    out = subprocess.run(['git', '-C', str(repo), *args], check=True,
                         capture_output=True, text=True, env=env)
    return out.stdout


LICENSE_LINES = [
    '// Copyright 2026 The Nomulus Authors. All Rights Reserved.',
    '//',
    '// Licensed under the Apache License, Version 2.0 (the "License");',
    '// you may not use this file except in compliance with the License.',
    '// You may obtain a copy of the License at',
    '//',
    '//     http://www.apache.org/licenses/LICENSE-2.0',
    '//',
    '// Unless required by applicable law or agreed to in writing, software',
    '// distributed under the License is distributed on an "AS IS" BASIS,',
    '// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.',
    '// See the License for the specific language governing permissions and',
    '// limitations under the License.',
]
LICENSE = '\n'.join(LICENSE_LINES) + '\n'

USER_SERVICE = LICENSE + '''
package google.registry.core.service;

import java.util.Map;

/** Resolves the display name of a registrar user. */
public final class UserServiceImpl {

  private final Map<String, String> displayNames;

  public UserServiceImpl(Map<String, String> displayNames) {
    this.displayNames = displayNames;
  }

  /** Returns the display name registered for {@code userId}, or the user id itself. */
  public String displayName(String userId) {
    String displayName = displayNames.get(userId);
    if (displayName == null) {
      return userId;
    }
    return displayName;
  }
}
'''

USER_SERVICE_TEST = LICENSE + '''
package google.registry.core.service;

import static org.junit.Assert.assertEquals;

import java.util.Map;
import org.junit.Test;

/** Unit tests for {@link UserServiceImpl}. */
public final class UserServiceImplTest {

  @Test
  public void displayName_returnsRegisteredName() {
    UserServiceImpl service = new UserServiceImpl(Map.of("user-1", "Ada Lovelace"));
    assertEquals("Ada Lovelace", service.displayName("user-1"));
  }

  @Test
  public void displayName_fallsBackToUserId() {
    UserServiceImpl service = new UserServiceImpl(Map.of());
    assertEquals("user-2", service.displayName("user-2"));
  }
}
'''

BUILD_GRADLE = '''// Copyright 2026 The Nomulus Authors. All Rights Reserved.
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}
'''

GRADLEW = '''#!/bin/sh
# Offline build stub: the real Gradle distribution is not part of this image, so every invoked
# task reports success. The pr-polisher checklist only cares that the command can be run.
echo "offline stub: gradle $* (no JDK in image; nothing executed)"
exit 0
'''

README = '''# registry-core (offline fixture)

A trimmed, Nomulus-shaped Java repository used to exercise the `pr-polisher` checklist.

- default branch: `main`
- feature branch: `feature/user-service-polish`
- `./gradlew` is an offline stub: there is no JDK in this image.

Java code in this repository is **not compiled** by the image.
'''

PACKAGE_LOCK = '{\n  "name": "console-webapp",\n  "version": "1.0.0",\n  "lockfileVersion": 3\n}\n'

# The baseline is committed first and never appears in any diff, so it may carry the very
# anti-patterns the checklist looks for. Keep them here instead of in the feature commit.
BASELINE_LEGACY = LICENSE + '''
package google.registry.core.service;

import java.time.Instant;
import java.time.ZoneId;
import java.util.HashMap;

/** Legacy helpers retained until the call sites are migrated. */
public final class LegacyUserSupport {

  /** Returns the current timestamp as text; kept for the legacy export format. */
  public String exportStamp() {
    HashMap<String, String> scratch = new HashMap<>();
    scratch.put("zone", ZoneId.of("UTC").getId());
    return Instant.now().toString();
  }
}
'''


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')


BASELINE_FILES = {
    'README.md': README,
    'build.gradle': BUILD_GRADLE,
    'settings.gradle': "// Copyright 2026 The Nomulus Authors. All Rights Reserved.\nrootProject.name = 'registry-core'\n",
    'gradlew': GRADLEW,
    'console-webapp/package-lock.json': PACKAGE_LOCK,
    'core/src/main/java/google/registry/core/service/UserServiceImpl.java': USER_SERVICE,
    'core/src/main/java/google/registry/core/service/LegacyUserSupport.java': BASELINE_LEGACY,
    'core/src/test/java/google/registry/core/service/UserServiceImplTest.java': USER_SERVICE_TEST,
}


SKILL_SCRIPT = (REPO / 'wildskills' / 'scripts_skills'
                / 'google-nomulus-gemini-skills-pr-polisher-skill-md' / 'scripts' / 'check_diff.py')
SCRIPT_IN_REPO = 'tools/pr-polisher/scripts/check_diff.py'
CHECK_DIFF_PRISTINE = TASK / 'environment' / 'check_diff.pristine.py'


def init_repo(root: Path, files: dict[str, str], branch: str = 'main') -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    write_tree(root, files)
    # The harness uploads environment/skills/ at run time per arm (empty in the NoSkill arm), so
    # the audited script is also baked into the repository itself. write_tree only handles text,
    # so the script copy is placed here, before the baseline commit.
    script_dst = root / SCRIPT_IN_REPO
    script_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SKILL_SCRIPT, script_dst)
    # `write_text` creates files 0644; the offline gradle stub has to be runnable for the
    # checklist's formatting step (`./gradlew ...`) to pass.
    (root / 'gradlew').chmod(0o755)
    git(root, 'init', '-q', '-b', branch)
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '-m', 'Import the registry-core fixture baseline',
        date=BASELINE_DATE)


def commit_files(root: Path, files: dict[str, str], message: str) -> None:
    write_tree(root, files)
    git(root, 'add', '-A')
    lines = message.split('\n')
    args = ['commit', '-q']
    for line in lines:
        args += ['-m', line]
    git(root, *args, date=FEATURE_DATE)


# --------------------------------------------------------------------------- delivered repo
# The one-commit feature branch shipped to the agent. Diff vs main contains exactly one
# WARNING-level finding and nothing at ERROR level:
#   * new Java file, correct 2026 copyright header;
#   * `catch (Exception e)` -> WARNING (generic catch);
#   * no trailing whitespace, no TODO/FIXME, no debug prints, no clock/zone violations;
#   * a matching test file, so the missing-test check passes.
DELIVERED_SERVICE = LICENSE + '''
package google.registry.core.service;

import java.util.Map;

/** Resolves the display name of a registrar user. */
public final class UserServiceImpl {

  private final Map<String, String> displayNames;

  public UserServiceImpl(Map<String, String> displayNames) {
    this.displayNames = displayNames;
  }

  /** Returns the display name registered for {@code userId}, or the user id itself. */
  public String displayName(String userId) {
    try {
      String displayName = displayNames.get(userId);
      if (displayName == null) {
        return userId;
      }
      return displayName;
    } catch (Exception e) {
      return userId;
    }
  }
}
'''

DELIVERED_TEST = LICENSE + '''
package google.registry.core.service;

import static org.junit.Assert.assertEquals;

import java.util.Map;
import org.junit.Test;

/** Unit tests for {@link UserServiceImpl}. */
public final class UserServiceImplTest {

  @Test
  public void displayName_fallsBackWhenAbsent() {
    UserServiceImpl service = new UserServiceImpl(Map.of());
    assertEquals("user-2", service.displayName("user-2"));
  }
}
'''

DELIVERED_MESSAGE = (
    'Add a display-name fallback to UserServiceImpl\n'
    '\n'
    'The console shows an empty cell when a registrar user has no registered display name.\n'
    'Falling back to the raw user id keeps the column readable, and the new test pins the\n'
    'absent-user behaviour.\n'
)


def build_environment_repo() -> None:
    root = ENV_REPO
    # Task-owned build input for the Dockerfile: the pristine script bytes, so the image does not
    # depend on environment/skills/ (which the harness swaps per arm at run time).
    shutil.copyfile(SKILL_SCRIPT, CHECK_DIFF_PRISTINE)
    init_repo(root, BASELINE_FILES)
    git(root, 'checkout', '-q', '-b', 'feature/user-service-polish')
    commit_files(root, {
        'core/src/main/java/google/registry/core/service/UserServiceImpl.java': DELIVERED_SERVICE,
        'core/src/test/java/google/registry/core/service/UserServiceImplTest.java': DELIVERED_TEST,
    }, DELIVERED_MESSAGE)
    (root / 'gradlew').chmod(0o755)
    print(f'built {root.relative_to(REPO)} (branch feature/user-service-polish)')
    print(f'copied {CHECK_DIFF_PRISTINE.relative_to(REPO)}')


# --------------------------------------------------------------------------- hidden fixtures
WARNING_ONLY_MESSAGE = (
    'Add a display-name fallback to UserServiceImpl\n'
    '\n'
    'The console shows an empty cell when a registrar user has no registered display name.\n'
    'The generic catch mirrors the surrounding Nomulus services and can be narrowed once the\n'
    'lookup API exposes its error cases.\n'
)

WARNING_ONLY_SERVICE = LICENSE + '''
package google.registry.core.service;

import java.util.Map;

/** Resolves the display name of a registrar user. */
public final class UserServiceImpl {

  private final Map<String, String> displayNames;

  public UserServiceImpl(Map<String, String> displayNames) {
    this.displayNames = displayNames;
  }

  /** Returns the display name registered for {@code userId}, or the user id itself. */
  public String displayName(String userId) {
    try {
      String displayName = displayNames.get(userId);
      if (displayName == null) {
        return userId;
      }
      return displayName;
    } catch (Exception e) {
      return userId;
    }
  }
}
'''

WARNING_ONLY_TEST = LICENSE + '''
package google.registry.core.service;

import static org.junit.Assert.assertEquals;

import java.util.Map;
import org.junit.Test;

/** Unit tests for {@link UserServiceImpl}. */
public final class UserServiceImplTest {

  @Test
  public void displayName_fallsBackWhenAbsent() {
    UserServiceImpl service = new UserServiceImpl(Map.of());
    assertEquals("user-2", service.displayName("user-2"));
  }
}
'''

CLEAN_MESSAGE = (
    'Add a currency formatter for registrar invoices\n'
    '\n'
    'Invoice totals are rendered by hand in three places. A single formatter keeps rounding\n'
    'consistent, and the accompanying test pins the two-decimal output.\n'
)

CLEAN_FORMATTER = LICENSE + '''
package google.registry.core.service;

import java.math.BigDecimal;
import java.math.RoundingMode;

/** Formats invoice amounts for the console. */
public final class InvoiceAmountFormatter {

  /** Returns {@code amount} rounded to two decimals, always with two fraction digits. */
  public String format(BigDecimal amount) {
    return amount.setScale(2, RoundingMode.HALF_UP).toPlainString();
  }
}
'''

CLEAN_FORMATTER_TEST = LICENSE + '''
package google.registry.core.service;

import static org.junit.Assert.assertEquals;

import java.math.BigDecimal;
import org.junit.Test;

/** Unit tests for {@link InvoiceAmountFormatter}. */
public final class InvoiceAmountFormatterTest {

  @Test
  public void format_roundsHalfUp() {
    assertEquals("1.01", new InvoiceAmountFormatter().format(new BigDecimal("1.005")));
  }
}
'''

MAIN_AHEAD_1_MESSAGE = (
    'Extract the display-name fallback into a helper\n'
    '\n'
    'The fallback is needed by the console and by the registrar export. Keeping it in one\n'
    'place avoids the two call sites drifting apart.\n'
)

MAIN_AHEAD_2_MESSAGE = (
    'Use the helper in the registrar export\n'
    '\n'
    'The export path still had its own copy of the fallback. Switching it to the shared helper\n'
    'removes the duplicate branch.\n'
)

MAIN_AHEAD_HELPER = LICENSE + '''
package google.registry.core.service;

/** Shared lookup helpers for registrar users. */
public final class UserDisplayNames {

  /** Returns {@code displayName} when present, otherwise {@code userId}. */
  public static String orUserId(String displayName, String userId) {
    if (displayName == null) {
      return userId;
    }
    return displayName;
  }
}
'''

MAIN_AHEAD_SERVICE = LICENSE + '''
package google.registry.core.service;

import java.util.Map;

/** Resolves the display name of a registrar user. */
public final class UserServiceImpl {

  private final Map<String, String> displayNames;

  public UserServiceImpl(Map<String, String> displayNames) {
    this.displayNames = displayNames;
  }

  /** Returns the display name registered for {@code userId}, or the user id itself. */
  public String displayName(String userId) {
    return UserDisplayNames.orUserId(displayNames.get(userId), userId);
  }
}
'''

MAIN_AHEAD_EXPORT = LICENSE + '''
package google.registry.core.service;

import java.util.Map;

/** Renders registrar users for the nightly export. */
public final class RegistrarExport {

  /** Returns the export cell for {@code userId}. */
  public String cell(Map<String, String> displayNames, String userId) {
    return UserDisplayNames.orUserId(displayNames.get(userId), userId);
  }
}
'''

NON_JAVA_FUNCTION = LICENSE.replace('//', '#') + '''
"""Console helpers bundled with the core module."""

import time


class RetryPolicy:
    """Retries a console fetch until the backend reports the asset is ready."""

    def wait_for_asset(self, attempts):
        for _ in range(attempts):
            if self._asset_ready():
                return True
            Thread.sleep(1000)
        return False

    def _asset_ready(self):
        return True
'''

NON_JAVA_MESSAGE = (
    'Add a console retry helper for pending assets\n'
    '\n'
    'The console currently gives up on the first poll. The helper waits for the backend to\n'
    'finish a pending asset so the download button stops flickering.\n'
)


def build_fixtures() -> None:
    if FIXTURES.exists():
        shutil.rmtree(FIXTURES)
    FIXTURES.mkdir(parents=True)
    scratch = Path(os.environ.get('WST13_FIXTURE_SCRATCH', '/tmp/wst13-pr-polisher-fixtures'))
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    # F1 warning-only: exactly one WARNING (generic catch), no ERROR anywhere.
    f1 = scratch / 'warning_only'
    init_repo(f1, BASELINE_FILES)
    git(f1, 'checkout', '-q', '-b', 'feature/task')
    commit_files(f1, {
        'core/src/main/java/google/registry/core/service/UserServiceImpl.java': WARNING_ONLY_SERVICE,
        'core/src/test/java/google/registry/core/service/UserServiceImplTest.java': WARNING_ONLY_TEST,
    }, WARNING_ONLY_MESSAGE)

    # F2 clean: zero ERRORs and zero WARNINGs.
    f2 = scratch / 'clean'
    init_repo(f2, BASELINE_FILES)
    git(f2, 'checkout', '-q', '-b', 'feature/task')
    commit_files(f2, {
        'core/src/main/java/google/registry/core/service/InvoiceAmountFormatter.java': CLEAN_FORMATTER,
        'core/src/test/java/google/registry/core/service/InvoiceAmountFormatterTest.java': CLEAN_FORMATTER_TEST,
    }, CLEAN_MESSAGE)

    # F3 main-ahead-2: the default branch is `main` and the feature branch is two commits ahead,
    # which must be reported as an ERROR (the pristine script only ever looks at `^master`).
    f3 = scratch / 'main_ahead_two'
    init_repo(f3, BASELINE_FILES)
    git(f3, 'checkout', '-q', '-b', 'feature/task')
    commit_files(f3, {
        'core/src/main/java/google/registry/core/service/UserDisplayNames.java': MAIN_AHEAD_HELPER,
        'core/src/main/java/google/registry/core/service/UserServiceImpl.java': MAIN_AHEAD_SERVICE,
    }, MAIN_AHEAD_1_MESSAGE)
    commit_files(f3, {
        'core/src/main/java/google/registry/core/service/RegistrarExport.java': MAIN_AHEAD_EXPORT,
    }, MAIN_AHEAD_2_MESSAGE)

    # F4 non-Java anti-pattern: the added `.py` line is WARNING-level and must be reported even
    # though the file is not Java (pristine `check_diff.py:205` skips it entirely).
    f4 = scratch / 'non_java'
    init_repo(f4, BASELINE_FILES)
    git(f4, 'checkout', '-q', '-b', 'feature/task')
    commit_files(f4, {
        'console-webapp/src/main/resources/console_retry.py': NON_JAVA_FUNCTION,
    }, NON_JAVA_MESSAGE)

    names = {
        'warning_only.tar': f1,
        'clean.tar': f2,
        'main_ahead_two.tar': f3,
        'non_java.tar': f4,
    }
    for tar_name, src in names.items():
        make_tar(src, FIXTURES / tar_name)
        print(f'built {FIXTURES.relative_to(REPO)}/{tar_name}')

    # Determinism / expectation self-check: regenerate a few times and compare digests.
    digests = {name: _digest(FIXTURES / name) for name in names}
    for tar_name, src in names.items():
        make_tar(src, scratch / 'check.tar')
        if _digest(scratch / 'check.tar') != digests[tar_name]:
            raise SystemExit(f'fixture {tar_name} is not reproducible')
    print('fixture reproducibility: OK')


def make_tar(src: Path, dest: Path) -> None:
    """Deterministic tar of ONE git repository (paths normalised, mtimes fixed).

    `.git/index` (stat cache, wall-clock dependent) and `.git/logs` (reflog, wall-clock
    timestamps) are excluded. The verifier rebuilds the index with `git read-tree HEAD` after
    unpacking, which is why the archives are byte-stable across builds.
    """
    entries: list[tuple[str, bytes, int]] = []
    for path in sorted(src.rglob('*')):
        rel = path.relative_to(src).as_posix()
        if path.is_dir():
            continue
        if rel == '.git/index' or rel.startswith('.git/logs/'):
            continue
        data = path.read_bytes()
        mode = 0o755 if os.access(path, os.X_OK) else 0o644
        entries.append((rel, data, mode))
    # Directories must be present too (empty dirs do not occur here, but be explicit).
    dirs = sorted({str(Path(rel).parent.as_posix()) for rel, _, _ in entries if '/' in rel})
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.GNU_FORMAT) as tar:
        for d in dirs:
            if d == '.':
                continue
            info = tarfile.TarInfo('./' + d + '/')
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            tar.addfile(info)
        for rel, data, mode in entries:
            info = tarfile.TarInfo('./' + rel)
            info.size = len(data)
            info.mode = mode
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            tar.addfile(info, io.BytesIO(data))
    dest.write_bytes(buf.getvalue())


def _digest(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    build_environment_repo()
    build_fixtures()
    return 0


if __name__ == '__main__':
    sys.exit(main())
