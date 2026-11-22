"""Speed-aware multi-mirror downloader & PyPI mirror selector for ListenScope Windows bootstrap.

Pure Python stdlib (zero third-party deps) so it can run inside a fresh Python 3.12/3.11
interpreter before any packages are installed:
- Emits structured progress markers `@@LS_PROGRESS|pct=...|stage=...|speed=...|mirror=...@@`
- Streams big CUDA wheels with rolling throughput measurement and automatically switches to the
  next mirror if throughput stays below threshold or stalls.
- Supports probing & ranking PyPI mirrors for fast `requirements-ai.txt` / `requirements-midi.txt`
  installation with fallback support.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import time
from typing import Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

PYTORCH_CU128_MIRRORS: tuple[tuple[str, str], ...] = (
    ("NJU 镜像", "https://mirrors.nju.edu.cn/pytorch/whl/cu128"),
    ("SJTU 镜像", "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128"),
    ("阿里云镜像", "https://mirrors.aliyun.com/pytorch-wheels/cu128"),
    ("PyTorch 官方源", "https://download.pytorch.org/whl/cu128"),
)

PYPI_MIRRORS: tuple[tuple[str, str], ...] = (
    ("清华 TUNA 镜像", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里云镜像", "https://mirrors.aliyun.com/pypi/simple"),
    ("中科大 USTC 镜像", "https://pypi.mirrors.ustc.edu.cn/simple"),
    ("PyPI 官方源", "https://pypi.org/simple"),
)

USER_AGENT = "ListenScope-Bootstrap/1.0"


def emit_progress(pct: int, stage: str, *, speed: str = "", mirror: str = "") -> None:
    clamped = max(0, min(100, int(pct)))
    safe_stage = stage.replace("|", "/").replace("@", "").strip()
    safe_speed = speed.replace("|", "/").replace("@", "").strip()
    safe_mirror = mirror.replace("|", "/").replace("@", "").strip()
    print(
        f"@@LS_PROGRESS|pct={clamped}|stage={safe_stage}|speed={safe_speed}|mirror={safe_mirror}@@",
        flush=True,
    )


def format_speed(bps: float) -> str:
    if bps <= 0.0:
        return "0 KB/s"
    if bps >= 1024.0 * 1024.0:
        return f"{bps / (1024.0 * 1024.0):.1f} MB/s"
    return f"{bps / 1024.0:.0f} KB/s"


class _SimpleIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        for key, val in attrs:
            if key.lower() == "href" and val:
                self.links.append(val)


def _fetch_text(url: str, timeout: float = 8.0) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def _probe_pypi_single(label: str, index_url: str, timeout: float = 2.8) -> tuple[bool, float, str, str]:
    probe_url = index_url.rstrip("/") + "/pip/"
    t0 = time.monotonic()
    try:
        req = Request(probe_url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) >= 400:
                return (False, 999.0, label, index_url)
            resp.read(4096)
        dt = time.monotonic() - t0
        return (True, dt, label, index_url)
    except Exception:
        return (False, 999.0, label, index_url)


def rank_pypi_mirrors(candidates: Iterable[tuple[str, str]] = PYPI_MIRRORS) -> list[tuple[str, str, float]]:
    items = list(candidates)
    results: list[tuple[bool, float, str, str]] = []
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(items)))) as pool:
        futs = [pool.submit(_probe_pypi_single, lbl, url) for lbl, url in items]
        for fut in as_completed(futs):
            results.append(fut.result())
    ok = [r for r in results if r[0]]
    bad = [r for r in results if not r[0]]
    ok.sort(key=lambda r: r[1])
    ranked: list[tuple[str, str, float]] = [(lbl, url, dt) for _, dt, lbl, url in ok]
    for _, dt, lbl, url in bad:
        ranked.append((lbl, url, dt))
    return ranked


def _parse_pkg_spec(spec: str) -> tuple[str, Optional[str]]:
    clean = spec.strip()
    if "==" in clean:
        pkg, ver = clean.split("==", 1)
        return pkg.strip().lower().replace("_", "-"), ver.strip().split("+")[0]
    return clean.lower().replace("_", "-"), None


def _match_wheel_href(
    links: list[str],
    *,
    base_url: str,
    pkg_name: str,
    pkg_version: Optional[str],
    cuda_tag: str,
    py_tag: str,
    plat_tag: str,
) -> Optional[tuple[str, str, Optional[str]]]:
    pkg_prefix = pkg_name.replace("-", "_") + "-"
    cuda_norm = f"+{cuda_tag.lower()}"
    best: Optional[tuple[str, str, Optional[str]]] = None
    for href in links:
        parsed = urlparse(href)
        fname = unquote(Path(parsed.path).name)
        if not fname.lower().endswith(".whl"):
            continue
        stem = fname[:-4]
        parts = stem.split("-")
        if len(parts) < 5:
            continue
        w_pkg, w_ver, w_py, w_abi, w_plat = parts[0], parts[1], parts[-3], parts[-2], parts[-1]
        if not fname.lower().startswith(pkg_prefix):
            continue
        if pkg_version and not w_ver.lower().startswith(pkg_version.lower()):
            continue
        if cuda_tag and cuda_norm not in w_ver.lower():
            continue
        if py_tag and w_py.lower() != py_tag.lower():
            continue
        if py_tag and w_abi.lower() not in (py_tag.lower(), "abi3", "none"):
            continue
        if plat_tag and w_plat.lower() not in (plat_tag.lower(), "any"):
            continue
        sha256_expected: Optional[str] = None
        if parsed.fragment:
            m = re.search(r"sha256=([0-9a-fA-F]{64})", parsed.fragment)
            if m:
                sha256_expected = m.group(1).lower()
        abs_url = urljoin(base_url, href)
        best = (abs_url, fname, sha256_expected)
        break
    return best


class _SlowMirrorError(RuntimeError):
    pass


def _download_with_speed_guard(
    url: str,
    dest: Path,
    *,
    pkg_name: str,
    mirror_label: str,
    expected_sha256: Optional[str],
    base_pct: int,
    span_pct: int,
    min_speed_bps: float,
    stall_sec: float,
    timeout_sec: float = 15.0,
    grace_sec: float = 7.0,
) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    if part.exists():
        try:
            part.unlink()
        except OSError:
            pass
    req = Request(url, headers={"User-Agent": USER_AGENT})
    t_start = time.monotonic()
    last_emit = t_start
    last_rx = t_start
    win_start = t_start
    win_bytes = 0
    total_rx = 0
    hasher = hashlib.sha256() if expected_sha256 else None

    with urlopen(req, timeout=timeout_sec) as resp:
        if getattr(resp, "status", 200) >= 400:
            raise HTTPError(url, resp.status, "HTTP error", resp.headers, None)
        try:
            total_size = int(resp.headers.get("Content-Length") or "0")
        except ValueError:
            total_size = 0

        with open(part, "wb") as out:
            while True:
                chunk = resp.read(256 * 1024)
                now = time.monotonic()
                if not chunk:
                    if now - last_rx > stall_sec and (total_size <= 0 or total_rx < total_size):
                        raise _SlowMirrorError(f"{mirror_label} 连接停滞超过 {stall_sec:.0f}s")
                    break
                out.write(chunk)
                if hasher is not None:
                    hasher.update(chunk)
                n = len(chunk)
                total_rx += n
                win_bytes += n
                last_rx = now

                elapsed_win = now - win_start
                elapsed_total = now - t_start
                cur_bps = win_bytes / max(0.05, elapsed_win) if elapsed_win >= 0.25 else (total_rx / max(0.05, elapsed_total))

                if elapsed_total >= grace_sec and elapsed_win >= grace_sec:
                    if cur_bps < min_speed_bps:
                        raise _SlowMirrorError(
                            f"{mirror_label} 速度过慢 ({format_speed(cur_bps)} < {format_speed(min_speed_bps)})"
                        )
                    win_start = now
                    win_bytes = 0

                if now - last_emit >= 0.45:
                    frac = (total_rx / total_size) if total_size > 0 else 0.0
                    pct = base_pct + int(round(frac * span_pct))
                    mb_done = total_rx / (1024.0 * 1024.0)
                    mb_tot = f"/{total_size / (1024.0 * 1024.0):.0f}MB" if total_size > 0 else "MB"
                    emit_progress(
                        pct,
                        f"下载 {pkg_name} ({mb_done:.0f}{mb_tot})",
                        speed=format_speed(cur_bps),
                        mirror=mirror_label,
                    )
                    last_emit = now

    if total_size > 0 and total_rx != total_size:
        part.unlink(missing_ok=True)
        raise _SlowMirrorError(f"{mirror_label} 下载不完整 ({total_rx}/{total_size} bytes)")

    if expected_sha256 and hasher is not None:
        actual = hasher.hexdigest().lower()
        if actual != expected_sha256.lower():
            part.unlink(missing_ok=True)
            raise RuntimeError(f"SHA256 校验失败: {dest.name}")

    part.replace(dest)


def fetch_cuda_wheels(
    *,
    wheel_dir: Path,
    specs: list[str],
    cuda_tag: str,
    py_tag: str,
    plat_tag: str,
    custom_index_url: str = "",
    min_speed_kbps: float = 150.0,
    stall_sec: float = 10.0,
    grace_sec: float = 7.0,
) -> int:
    wheel_dir.mkdir(parents=True, exist_ok=True)
    mirrors: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    if custom_index_url.strip():
        norm = custom_index_url.strip().rstrip("/")
        if norm != "https://download.pytorch.org/whl/cu128":
            mirrors.append(("自定义源", norm))
            seen_urls.add(norm)
    for lbl, url in PYTORCH_CU128_MIRRORS:
        norm = url.rstrip("/")
        if norm not in seen_urls:
            mirrors.append((lbl, norm))
            seen_urls.add(norm)

    total_pkgs = max(1, len(specs))
    per_span = max(1, 36 // total_pkgs)
    min_bps = max(32.0, float(min_speed_kbps)) * 1024.0

    for idx, raw_spec in enumerate(specs):
        pkg_name, pkg_ver = _parse_pkg_spec(raw_spec)
        base_pct = 16 + idx * per_span

        # Reuse pre-downloaded wheel if already verified in cache
        existing = [
            p for p in wheel_dir.glob(f"{pkg_name.replace('-', '_')}-*.whl")
            if (not pkg_ver or pkg_ver in p.name) and f"+{cuda_tag}" in p.name and py_tag in p.name and plat_tag in p.name
        ]
        if existing and existing[0].stat().st_size > 1024:
            print(f"[CACHE] 命中本地缓存 wheel: {existing[0].name}", flush=True)
            emit_progress(base_pct + per_span, f"已缓存 {pkg_name}", speed="缓存", mirror="本地目录")
            continue

        downloaded = False
        for m_idx, (m_label, m_url) in enumerate(mirrors):
            pkg_index = f"{m_url}/{pkg_name}/"
            try:
                emit_progress(base_pct, f"连接 {pkg_name} 索引…", mirror=m_label)
                html = _fetch_text(pkg_index, timeout=7.0)
                parser = _SimpleIndexParser()
                parser.feed(html)
                match = _match_wheel_href(
                    parser.links,
                    base_url=pkg_index,
                    pkg_name=pkg_name,
                    pkg_version=pkg_ver,
                    cuda_tag=cuda_tag,
                    py_tag=py_tag,
                    plat_tag=plat_tag,
                )
                if match is None:
                    print(f"[MIRROR] {m_label} 未收录匹配 {pkg_name} ({pkg_ver}+{cuda_tag})，切换下一源...", flush=True)
                    continue
                abs_url, fname, sha256_hex = match
                dest_whl = wheel_dir / unquote(fname)
                print(f"[MIRROR] 从 {m_label} 下载 {dest_whl.name}...", flush=True)
                _download_with_speed_guard(
                    abs_url,
                    dest_whl,
                    pkg_name=pkg_name,
                    mirror_label=m_label,
                    expected_sha256=sha256_hex,
                    base_pct=base_pct,
                    span_pct=per_span,
                    min_speed_bps=min_bps,
                    stall_sec=stall_sec,
                    grace_sec=grace_sec,
                )
                downloaded = True
                break
            except (_SlowMirrorError, HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
                next_hint = mirrors[m_idx + 1][0] if m_idx + 1 < len(mirrors) else "默认回退"
                print(f"[MIRROR] {m_label} 失败/过慢 ({exc}) -> 自动切换至 {next_hint}", flush=True)
                continue

        if not downloaded:
            print(f"[WARN] 所有镜像下载 {raw_spec} 未成功，将回退到 pip 多源重试安装。", flush=True)
            return 2

    emit_progress(54, "PyTorch cu128 下载就绪，开始本地安装…")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ListenScope Multi-Mirror Bootstrap Helper")
    parser.add_argument("--pick-pypi-mirror", action="store_true", help="Probe and print ranked PyPI mirrors")
    parser.add_argument("--fetch-cuda-wheels", action="store_true", help="Download matching CUDA wheels with slow-mirror failover")
    parser.add_argument("--wheel-dir", type=str, default="")
    parser.add_argument("--cuda-tag", type=str, default="cu128")
    parser.add_argument("--py-tag", type=str, default="cp312")
    parser.add_argument("--plat-tag", type=str, default="win_amd64")
    parser.add_argument("--index-url", type=str, default="")
    parser.add_argument("--min-speed-kbps", type=float, default=150.0)
    parser.add_argument("--stall-sec", type=float, default=10.0)
    parser.add_argument("--specs", nargs="*", default=[])
    args = parser.parse_args(argv)

    if args.pick_pypi_mirror:
        for lbl, url, _dt in rank_pypi_mirrors():
            print(f"{lbl}|{url}")
        return 0

    if args.fetch_cuda_wheels:
        if not args.wheel_dir or not args.specs:
            print("Missing --wheel-dir or --specs", file=sys.stderr)
            return 1
        return fetch_cuda_wheels(
            wheel_dir=Path(args.wheel_dir),
            specs=list(args.specs),
            cuda_tag=args.cuda_tag,
            py_tag=args.py_tag,
            plat_tag=args.plat_tag,
            custom_index_url=args.index_url,
            min_speed_kbps=args.min_speed_kbps,
            stall_sec=args.stall_sec,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
