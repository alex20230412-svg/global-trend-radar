"""Private-only Git persistence with one non-force publication per batch."""

import base64
from dataclasses import dataclass, field
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

import httpx


CODE_REPO = "alex20230412-svg/global-trend-radar"
DATA_REPO = "alex20230412-svg/global-trend-radar-data"
DATA_URL = f"https://github.com/{DATA_REPO}.git"
DATA_BRANCH = "main"
WARN_KIB = 256 * 1024
STOP_KIB = 512 * 1024
STORE_ROOTS = {"observations", "manifests", "runs", "reports", "deliveries", "health", "first-seen"}


class StorageError(Exception):
    """Fixed error codes only, suitable for the public Actions log."""

    def __init__(self, code, *, http_status=None):
        super().__init__(code)
        self.http_status = http_status


class PublicationError(StorageError):
    """The local clone may be ahead of the remote; abandon it for this run."""


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def github_object(path, token):
    if not token:
        raise StorageError("github_credential_missing")
    try:
        with httpx.Client(timeout=12, follow_redirects=False, trust_env=False) as client:
            with client.stream(
                "GET",
                f"https://api.github.com/repos/{path}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            ) as response:
                if response.status_code != 200:
                    raise StorageError("github_access_rejected", http_status=response.status_code)
                raw = bytearray()
                for chunk in response.iter_bytes(8192):
                    raw.extend(chunk)
                    if len(raw) > 256 * 1024:
                        raise StorageError("github_metadata_oversize")
        result = json.loads(raw)
    except (httpx.HTTPError, ValueError) as exc:
        raise StorageError("github_metadata_unavailable") from exc
    if not isinstance(result, dict):
        raise StorageError("github_invalid_metadata")
    return result


def private_repository_size(token, metadata=github_object):
    info = metadata(DATA_REPO, token)
    if (
        info.get("full_name") != DATA_REPO
        or info.get("private") is not True
        or info.get("visibility") != "private"
        or info.get("default_branch") != DATA_BRANCH
    ):
        raise StorageError("private_repository_required")
    size = info.get("size")
    if type(size) is not int or size < 0:
        raise StorageError("repository_size_unknown")
    if size >= STOP_KIB:
        raise StorageError("repository_capacity_stop")
    return size


def _run_git(args, cwd, env=None):
    try:
        result = subprocess.run(
            ["git", "-c", f"core.hooksPath={os.devnull}", *args],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StorageError("git_operation_unconfirmed") from exc
    if result.returncode:
        raise StorageError("git_operation_failed")


@dataclass
class PrivateGitStore:
    root: Path
    git_env: dict = field(repr=False)
    size_kib: int
    token: str = field(repr=False)

    @classmethod
    def clone(cls, parent, token):
        size = private_repository_size(token)
        root = Path(parent) / "private-data"
        git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        for key in ("DATA_REPO_TOKEN", "TELEGRAM_BOT_TOKEN", "RUN_METADATA_TOKEN", "GEMINI_API_KEY"):
            git_env.pop(key, None)
        credential = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        git_env.update({
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": f"http.{DATA_URL}.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credential}",
            "GIT_CONFIG_KEY_1": "http.followRedirects",
            "GIT_CONFIG_VALUE_1": "false",
        })
        _run_git([
            "clone", "--no-tags", "--depth", "1", "--single-branch", "--branch", DATA_BRANCH,
            "--", DATA_URL, str(root),
        ], root.parent, git_env)
        return cls(root, git_env, size, token)

    def _path(self, key):
        path = Path(key)
        if path.is_absolute() or len(path.parts) < 2 or path.parts[0] not in STORE_ROOTS or ".." in path.parts:
            raise StorageError("invalid_storage_key")
        result = self.root / path
        if result.absolute() != result.resolve():
            raise StorageError("storage_symlink_rejected")
        return result

    def read(self, key):
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def publish(self, files, message):
        try:
            self._publish(files, message)
        except StorageError as exc:
            raise PublicationError(str(exc), http_status=exc.http_status) from exc
        except OSError as exc:
            raise PublicationError("git_publication_failed") from exc

    def _publish(self, files, message):
        _write_files(self._path, files)
        if not files:
            return
        _run_git(["add", "--", *files], self.root, self.git_env)
        _run_git([
            "-c", "user.name=Global Trend Radar", "-c", "user.email=global-trend-radar@users.noreply.github.com",
            "-c", "commit.gpgsign=false", "commit", "-m", message,
        ], self.root, self.git_env)
        # A competing writer or ambiguous push aborts before the next side effect.
        private_repository_size(self.token)
        _run_git(["push", "--", DATA_URL, f"HEAD:refs/heads/{DATA_BRANCH}"], self.root, self.git_env)


def _write_files(resolve, files):
    for key, value in files.items():
        path = resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".staged")
        temp.write_bytes(value)
        os.replace(temp, path)


def read_json(store, key):
    content = store.read(key)
    return None if content is None else json.loads(content)


def archive_rows(rows):
    return gzip.compress(b"".join(json_bytes(row) for row in rows), mtime=0)


def read_observations(store, partition, manifest):
    content = store.read(f"observations/{partition}.jsonl.gz")
    if content is None or hashlib.sha256(content).hexdigest() != manifest["sha256"]:
        raise StorageError("observation_checksum_mismatch")
    try:
        rows = [json.loads(line) for line in gzip.decompress(content).splitlines()]
    except (OSError, ValueError) as exc:
        raise StorageError("observation_archive_invalid") from exc
    if len(rows) != manifest["row_count"]:
        raise StorageError("observation_count_mismatch")
    return rows
