"""
Regression test for commit f2f7da6:
  fix(infra): unify all production image tags on canonical release 1.1.0

Verifies infra/compose/docker-compose.prod.yml — after the fix — resolves
every factory-* service `image:` to the canonical :1.1.0 tag when no
FACTORY_IMAGE_TAG / FACTORY_IMAGE_REPO / BUILD_VERSION overrides are
supplied, and that env-var overrides still work.

This is a pure YAML / config regression test — NO docker binary, NO HTTP.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path("/app")
COMPOSE_FILE = REPO_ROOT / "infra" / "compose" / "docker-compose.prod.yml"
VERSION_FILE = REPO_ROOT / "VERSION"
CANONICAL_VERSION = "1.1.0"
FIX_COMMIT = "f2f7da6"

FACTORY_SERVICES = ["factory-backend", "factory-vie", "factory-frontend", "factory-runner"]

# ── docker-compose ${VAR:-default} substitution emulator ────────────────
# Semantics: when VAR is unset OR empty, substitute `default`.
_VAR_PATTERN = re.compile(r"\$\{(\w+):-([^}]*)\}")


def resolve_compose_vars(value: str, env: dict) -> str:
    """Emulate docker-compose ${VAR:-default} substitution."""
    if not isinstance(value, str):
        return value

    def _sub(match):
        var_name, default = match.group(1), match.group(2)
        v = env.get(var_name)
        return v if v else default

    prev = None
    out = value
    # Iterate for nested / repeated substitutions (idempotent when done)
    while prev != out:
        prev = out
        out = _VAR_PATTERN.sub(_sub, out)
    return out


# ── Fixtures ────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def compose_yaml():
    assert COMPOSE_FILE.exists(), f"Compose file missing: {COMPOSE_FILE}"
    with open(COMPOSE_FILE, "r") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def compose_text():
    return COMPOSE_FILE.read_text()


# ── Feature 1 & 2: default resolution of image: strings ────────────────
class TestDefaultImageResolution:
    """With NO env overrides, every image: must resolve to strategy-factory/<name>:1.1.0."""

    def test_all_four_factory_services_present(self, compose_yaml):
        services = compose_yaml.get("services", {})
        for svc in FACTORY_SERVICES:
            assert svc in services, f"Missing service block: {svc}"

    @pytest.mark.parametrize(
        "service,expected",
        [
            ("factory-backend", "strategy-factory/backend:1.1.0"),
            ("factory-vie", "strategy-factory/vie:1.1.0"),
            ("factory-frontend", "strategy-factory/frontend:1.1.0"),
            ("factory-runner", "strategy-factory/backend:1.1.0"),
        ],
    )
    def test_default_image_resolves_to_1_1_0(self, compose_yaml, service, expected):
        raw = compose_yaml["services"][service]["image"]
        # Empty env → all defaults kick in
        resolved = resolve_compose_vars(raw, env={})
        assert resolved == expected, (
            f"{service}: expected image {expected!r}, got {resolved!r} "
            f"(raw template: {raw!r})"
        )

    def test_backend_and_runner_resolve_to_identical_image(self, compose_yaml):
        """factory-backend & factory-runner build the SAME Dockerfile → must publish identical tag."""
        env = {}
        b = resolve_compose_vars(compose_yaml["services"]["factory-backend"]["image"], env)
        r = resolve_compose_vars(compose_yaml["services"]["factory-runner"]["image"], env)
        assert b == r, (
            f"factory-backend and factory-runner resolve to DIFFERENT images: "
            f"backend={b!r}, runner={r!r}. They share ../../backend Dockerfile "
            f"and MUST publish the identical tag."
        )
        assert b == f"strategy-factory/backend:{CANONICAL_VERSION}"


# ── Feature 3: BUILD_VERSION defaults ──────────────────────────────────
class TestBuildVersionDefaults:
    """All BUILD_VERSION default fallbacks must be 1.1.0."""

    def test_backend_build_arg_build_version(self, compose_yaml):
        args = compose_yaml["services"]["factory-backend"]["build"]["args"]
        assert resolve_compose_vars(args["BUILD_VERSION"], env={}) == CANONICAL_VERSION

    def test_backend_env_build_version(self, compose_yaml):
        env_block = compose_yaml["services"]["factory-backend"]["environment"]
        assert resolve_compose_vars(env_block["BUILD_VERSION"], env={}) == CANONICAL_VERSION

    def test_runner_build_arg_build_version(self, compose_yaml):
        args = compose_yaml["services"]["factory-runner"]["build"]["args"]
        assert resolve_compose_vars(args["BUILD_VERSION"], env={}) == CANONICAL_VERSION


# ── Feature 2 (grep): no residual 1.0.0 anywhere in the file ───────────
class TestNoResidualOldVersion:
    def test_no_1_0_0_string_in_file(self, compose_text):
        # After the fix, no 1.0.0 should appear anywhere in this file.
        matches = re.findall(r"1\.0\.0", compose_text)
        assert matches == [], (
            f"Residual '1.0.0' occurrences found in {COMPOSE_FILE} "
            f"(count={len(matches)}). Fix is incomplete."
        )

    def test_grep_confirms_zero_1_0_0(self):
        # Independent verification via shell grep
        result = subprocess.run(
            ["grep", "-c", "1\\.0\\.0", str(COMPOSE_FILE)],
            capture_output=True,
            text=True,
        )
        # grep -c prints count; exit 1 with count 0 when no matches
        count = int(result.stdout.strip() or "0")
        assert count == 0, f"grep found {count} occurrences of '1.0.0' in prod compose"


# ── Feature 4: env override regression — ${VAR:-default} still functions ─
class TestEnvOverrideRegression:
    def test_factory_image_tag_override(self, compose_yaml):
        env = {"FACTORY_IMAGE_TAG": "1.2.3"}
        for svc in FACTORY_SERVICES:
            resolved = resolve_compose_vars(compose_yaml["services"][svc]["image"], env)
            assert resolved.endswith(":1.2.3"), (
                f"{svc}: FACTORY_IMAGE_TAG override failed → {resolved!r}"
            )

    def test_factory_image_repo_override(self, compose_yaml):
        env = {"FACTORY_IMAGE_REPO": "ghcr.io/example"}
        for svc in FACTORY_SERVICES:
            resolved = resolve_compose_vars(compose_yaml["services"][svc]["image"], env)
            assert resolved.startswith("ghcr.io/example/"), (
                f"{svc}: FACTORY_IMAGE_REPO override failed → {resolved!r}"
            )

    def test_both_overrides_together(self, compose_yaml):
        env = {"FACTORY_IMAGE_REPO": "ghcr.io/example", "FACTORY_IMAGE_TAG": "9.9.9"}
        expected_suffixes = {
            "factory-backend": "/backend:9.9.9",
            "factory-vie": "/vie:9.9.9",
            "factory-frontend": "/frontend:9.9.9",
            "factory-runner": "/backend:9.9.9",
        }
        for svc, suf in expected_suffixes.items():
            resolved = resolve_compose_vars(compose_yaml["services"][svc]["image"], env)
            assert resolved == f"ghcr.io/example{suf}", (
                f"{svc}: expected ghcr.io/example{suf}, got {resolved!r}"
            )

    def test_build_version_override(self, compose_yaml):
        env = {"BUILD_VERSION": "9.9.9"}
        args = compose_yaml["services"]["factory-backend"]["build"]["args"]
        assert resolve_compose_vars(args["BUILD_VERSION"], env) == "9.9.9"
        env_block = compose_yaml["services"]["factory-backend"]["environment"]
        assert resolve_compose_vars(env_block["BUILD_VERSION"], env) == "9.9.9"
        r_args = compose_yaml["services"]["factory-runner"]["build"]["args"]
        assert resolve_compose_vars(r_args["BUILD_VERSION"], env) == "9.9.9"


# ── Feature 5: commit scope — exactly 1 file, +5 / -5 lines ───────────
class TestCommitScope:
    def test_git_show_stat_reports_one_file(self):
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", "--stat", "--format=", FIX_COMMIT],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        out = result.stdout.strip()
        # Expected format:
        #  infra/compose/docker-compose.prod.yml | 10 +++++-----
        #  1 file changed, 5 insertions(+), 5 deletions(-)
        assert "infra/compose/docker-compose.prod.yml" in out
        assert "1 file changed" in out
        assert "5 insertions(+)" in out
        assert "5 deletions(-)" in out

    def test_only_prod_compose_file_touched(self):
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", "--name-only", "--format=", FIX_COMMIT],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        files = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        assert files == ["infra/compose/docker-compose.prod.yml"], (
            f"Commit touched files outside expected scope: {files}"
        )

    def test_no_forbidden_paths_in_commit(self):
        """Ensure no changes under backend/, frontend/, vie/, infra/caddy/, infra/scripts/, docs/."""
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", "--name-only", "--format=", FIX_COMMIT],
            capture_output=True,
            text=True,
        )
        files = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        forbidden = ("backend/", "frontend/", "vie/", "infra/caddy/", "infra/scripts/", "docs/")
        offenders = [f for f in files if f.startswith(forbidden)]
        assert offenders == [], f"Commit modified forbidden paths: {offenders}"


# ── Consistency: canonical release string vs /app/VERSION ──────────────
class TestCanonicalVersionConsistency:
    def test_version_file_matches_canonical(self):
        assert VERSION_FILE.read_text().strip() == CANONICAL_VERSION
