"""GPU model-swap scheduler for a single 24–48GB card.

Heavy models (MiniMax H3) take an *exclusive* lease: every other service is
unloaded first. Lighter services (VoxCPM2, ACE-Step, Qwen with MoE experts on
CPU) share the card while their summed VRAM fits the budget; otherwise the
least-recently-used idle service is stopped.

Every lease is timed so the cost tracker can bill GPU-seconds → kWh → money.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

import httpx

from ..config import settings
from ..log import get_logger

log = get_logger("gpu")


def nvidia_smi() -> list[dict]:
    """Return per-GPU memory/utilisation, or [] when nvidia-smi is unavailable."""
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,power.draw",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001
        return []
    gpus = []
    for line in out.strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 6:
            gpus.append({"index": int(p[0]), "name": p[1], "total_mb": float(p[2]), "used_mb": float(p[3]),
                         "util": float(p[4]), "power_w": float(p[5]) if p[5] not in ("[N/A]", "") else None})
    return gpus


def gpu_apps() -> list[dict]:
    """Processes currently holding GPU memory (pid, name, MiB)."""
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001
        return []
    apps = []
    for line in out.strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 3 and p[0].isdigit():
            apps.append({"pid": int(p[0]), "name": p[1], "mb": float(p[2]) if p[2].replace(".", "").isdigit() else 0.0})
    return apps


def _descendants(pid: int) -> set[int]:
    try:
        out = subprocess.run(["ps", "-e", "-o", "pid=,pgid="], capture_output=True, text=True).stdout
    except Exception:  # noqa: BLE001
        return {pid}
    return {int(a) for a, b in (l.split() for l in out.strip().splitlines() if len(l.split()) == 2) if int(b) == pid} | {pid}


@dataclass
class Service:
    name: str
    cfg: dict
    proc: subprocess.Popen | None = None
    external: bool = False            # started by the user, not by us
    leases: int = 0
    last_used: float = 0.0
    gpu_seconds: float = 0.0
    log_path: Path | None = None
    adopted_pid: int | None = None    # started by an earlier Midea process (e.g. before a board restart)

    @property
    def pid_file(self) -> Path:
        return settings().root / ".logs" / f"{self.name}.pid"

    def adopt(self) -> bool:
        """Re-attach to a service a previous Midea process started, so it is managed (and stoppable)."""
        try:
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, 0)
        except (OSError, ValueError):
            return False
        if self.healthy(1.0):
            self.adopted_pid = pid
            return True
        return False

    @property
    def vram(self) -> float:
        return float(self.cfg.get("vram_gb", 0))

    @property
    def exclusive(self) -> bool:
        return bool(self.cfg.get("exclusive", False))

    @property
    def in_process(self) -> bool:
        return bool(self.cfg.get("in_process", False))

    def healthy(self, timeout: float = 2.0) -> bool:
        url = self.cfg.get("health")
        if not url:
            return self.in_process or (self.proc is not None and self.proc.poll() is None)
        try:
            return httpx.get(url, timeout=timeout).status_code < 500
        except Exception:  # noqa: BLE001
            return False

    @property
    def running(self) -> bool:
        if self.in_process:
            return self.leases > 0
        if self.adopted_pid:
            try:
                os.kill(self.adopted_pid, 0)
                return True
            except OSError:
                self.adopted_pid = None
        return self.external or (self.proc is not None and self.proc.poll() is None)

    def start(self) -> None:
        if self.in_process:
            return
        if self.healthy():
            self.external = self.proc is None
            return
        if str(self.cfg.get("external", False)).lower() in ("true", "1", "yes"):
            raise RuntimeError(f"{self.name}: external endpoint {self.cfg.get('health') or self.cfg.get('base_url')} "
                               f"is not responding — start that service (Midea does not manage it)")
        cmd = self.cfg.get("start")
        if not cmd:
            raise RuntimeError(f"service {self.name} has no start command and is not reachable")
        cwd = os.path.expanduser(self.cfg.get("cwd", str(settings().root)))
        logs = settings().root / ".logs"
        logs.mkdir(exist_ok=True)
        self.log_path = logs / f"{self.name}.log"
        env = dict(os.environ)
        env.setdefault("CUDA_VISIBLE_DEVICES", str(settings().get("gpu.device", 0)))
        env["PYTHONPATH"] = f"{settings().root}{os.pathsep}{env.get('PYTHONPATH', '')}"
        log.info("starting %s: %s", self.name, cmd)
        fh = open(self.log_path, "ab")
        self.proc = subprocess.Popen(cmd, shell=True, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT,
                                     env=env, start_new_session=True)
        self.pid_file.write_text(str(self.proc.pid))
        deadline = time.time() + float(self.cfg.get("startup_timeout_s", 300))
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"{self.name} exited with {self.proc.returncode}; see {self.log_path}")
            if self.healthy():
                log.info("%s is ready", self.name)
                return
            time.sleep(2)
        self.stop()
        raise TimeoutError(f"{self.name} did not become healthy; see {self.log_path}")

    def stop(self) -> None:
        if self.adopted_pid:
            log.info("stopping %s (adopted pid %d) to free %.1f GB", self.name, self.adopted_pid, self.vram)
            for sig in (signal.SIGTERM, signal.SIGKILL):
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(self.adopted_pid, sig)
                for _ in range(30):
                    try:
                        os.kill(self.adopted_pid, 0)
                        time.sleep(1)
                    except OSError:
                        break
                else:
                    continue
                break
            self.adopted_pid = None
            self.pid_file.unlink(missing_ok=True)
            return
        if self.external:
            log.warning("%s was started externally; leaving it running (stop it yourself to free VRAM)", self.name)
            return
        if self.proc is None or self.proc.poll() is not None:
            self.proc = None
            return
        log.info("stopping %s to free %.1f GB", self.name, self.vram)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(self.proc.pid, signal.SIGTERM)
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.proc.pid, signal.SIGKILL)
        self.proc = None
        self.pid_file.unlink(missing_ok=True)


@dataclass
class GPUScheduler:
    services: dict[str, Service] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)
    on_usage: Callable[[str, float], None] | None = None   # (service, gpu_seconds)

    @classmethod
    def from_settings(cls) -> "GPUScheduler":
        s = settings()
        sch = cls({name: Service(name, cfg) for name, cfg in s.services.items()})
        for sv in sch.services.values():
            if not sv.in_process and not s.mocked(sv.name) and sv.adopt():
                log.info("adopted running %s (pid %d)", sv.name, sv.adopted_pid)
        return sch

    @property
    def budget_gb(self) -> float:
        s = settings()
        return float(s.get("gpu.vram_gb", 24)) - float(s.get("gpu.reserve_gb", 1.5))

    def resident_gb(self) -> float:
        return sum(sv.vram for sv in self.services.values() if sv.running and not sv.external and not sv.in_process)

    def status(self) -> dict:
        fgb, other = self.foreign_gb() if settings().mode != "mock" else (0.0, [])
        return {
            "budget_gb": self.budget_gb, "foreign_gb": round(fgb, 1), "foreign": other,
            "resident_gb": self.resident_gb(),
            "gpus": nvidia_smi(),
            "services": {n: {"running": sv.running, "external": sv.external, "leases": sv.leases,
                             "vram_gb": sv.vram, "exclusive": sv.exclusive, "gpu_seconds": round(sv.gpu_seconds, 1),
                             "model": sv.cfg.get("model")} for n, sv in self.services.items()},
        }

    def _make_room(self, target: Service) -> None:
        others = [sv for sv in self.services.values() if sv is not target and sv.running]
        if target.exclusive:
            busy = [sv.name for sv in others if sv.leases > 0]
            if busy:
                raise RuntimeError(f"{target.name} needs the whole GPU but {busy} are busy")
            for sv in others:
                sv.stop()
            return
        for sv in others:            # an exclusive service never shares
            if sv.exclusive and sv.leases == 0:
                sv.stop()
        idle = sorted((sv for sv in others if sv.leases == 0 and sv.running), key=lambda s: s.last_used)
        while self.resident_gb() + target.vram > self.budget_gb and idle:
            idle.pop(0).stop()
        if self.resident_gb() + target.vram > self.budget_gb:
            raise RuntimeError(f"not enough VRAM for {target.name} ({target.vram} GB); "
                               f"{self.resident_gb():.1f}/{self.budget_gb:.1f} GB in use by busy services")

    def own_pids(self) -> set[int]:
        pids: set[int] = {os.getpid()}
        for sv in self.services.values():
            if sv.proc is not None and sv.proc.poll() is None:
                pids |= _descendants(sv.proc.pid)
            if sv.adopted_pid:
                pids |= _descendants(sv.adopted_pid)
        return pids

    def foreign_gb(self) -> tuple[float, list[dict]]:
        """VRAM held by processes Midea does not manage (other users / other jobs on a shared GPU)."""
        mine = self.own_pids()
        other = [a for a in gpu_apps() if a["pid"] not in mine]
        return sum(a["mb"] for a in other) / 1024, other

    def _check_physical(self, target: Service) -> None:
        g = nvidia_smi()
        if not g:
            return
        idx = int(settings().get("gpu.device", 0))
        g = next((x for x in g if x["index"] == idx), g[0])
        # min_vram_gb: what the service can actually start with (ComfyUI --lowvram streams weights from RAM)
        need = float(target.cfg.get("min_vram_gb", target.vram)) + float(settings().get("gpu.reserve_gb", 1.5))
        deadline = time.time() + 30                 # give stopped services time to release memory
        while True:
            g = next((x for x in nvidia_smi() if x["index"] == idx), g)
            free = (g["total_mb"] - g["used_mb"]) / 1024
            if free >= need or time.time() > deadline:
                break
            time.sleep(2)
        if free < need:
            fgb, other = self.foreign_gb()
            who = ", ".join(f"pid {a['pid']} {a['name']} {a['mb']/1024:.1f}GB" for a in other) or "unknown"
            raise RuntimeError(f"{target.name} needs ~{need:.0f} GB VRAM but only {free:.1f} GB is free on GPU {idx}. "
                               f"Held by processes outside Midea: {who}. Free that memory or lower "
                               f"services.{target.name}.vram_gb / resolution.")

    @contextlib.contextmanager
    def lease(self, name: str) -> Iterator[Service]:
        sv = self.services[name]
        with self.lock:
            if not settings().mocked(name) and not sv.running:
                self._make_room(sv)
                if not sv.healthy(1.0):
                    self._check_physical(sv)
                sv.start()
            sv.leases += 1
        t0 = time.time()
        try:
            yield sv
        finally:
            dt = time.time() - t0
            with self.lock:
                sv.leases -= 1
                sv.last_used = time.time()
                sv.gpu_seconds += dt
            if self.on_usage:
                self.on_usage(name, dt)

    def unload_idle(self) -> list[str]:
        ttl = float(settings().get("gpu.idle_unload_s", 600))
        stopped = []
        with self.lock:
            for sv in self.services.values():
                if sv.running and sv.leases == 0 and not sv.external and time.time() - sv.last_used > ttl:
                    sv.stop()
                    stopped.append(sv.name)
        return stopped

    def shutdown(self) -> None:
        with self.lock:
            for sv in self.services.values():
                sv.stop()


_scheduler: GPUScheduler | None = None


def scheduler() -> GPUScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = GPUScheduler.from_settings()
    return _scheduler
