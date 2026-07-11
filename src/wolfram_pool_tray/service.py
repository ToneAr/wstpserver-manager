from __future__ import annotations

import glob
import os
import plistlib
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import ensure_config

SERVICE_NAME = "wstpserver.service"
LAUNCHD_LABEL = "com.wolfram.wstpserver"
WINDOWS_TASK_NAME = "WolframKernelPool"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 31415


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return "\n".join(part for part in (self.stdout.strip(), self.stderr.strip()) if part)


@dataclass(frozen=True)
class ServicePaths:
    config_file: Path
    log_file: Path
    service_file: Path | None


@dataclass(frozen=True)
class ServiceStatus:
    installed: bool
    running: bool
    enabled: bool | None
    detail: str
    kernel_process_count: int | None = None


@dataclass(frozen=True)
class DetectionResult:
    wstpserver_bin: Path | None
    kernel_bin: Path | None
    notes: tuple[str, ...]


class ServiceError(RuntimeError):
    pass


class BaseServiceManager:
    name = "unsupported"

    def paths(self) -> ServicePaths:
        raise NotImplementedError

    def detect_binaries(self) -> DetectionResult:
        kernel = self._detect_kernel()
        notes: list[str] = []
        if kernel:
            notes.append(f"Detected kernel: {kernel}")
        else:
            notes.append("Could not auto-detect WolframKernel")

        wstpserver = self._find_wstpserver_from_kernel(kernel) if kernel else None
        if not wstpserver:
            wstpserver = self._detect_wstpserver()
        if wstpserver:
            notes.append(f"Detected wstpserver: {wstpserver}")
        else:
            notes.append("Could not auto-detect wstpserver")

        return DetectionResult(wstpserver, kernel, tuple(notes))

    def install(self, wstpserver_bin: Path | None = None, kernel_bin: Path | None = None) -> str:
        detection = self.detect_binaries()
        wstpserver = wstpserver_bin or detection.wstpserver_bin
        kernel = kernel_bin or detection.kernel_bin
        if not kernel:
            raise ServiceError("Could not find WolframKernel. Choose it manually and try again.")
        if not wstpserver:
            raise ServiceError("Could not find wstpserver. Choose it manually and try again.")
        if not kernel.exists():
            raise ServiceError(f"Kernel path does not exist: {kernel}")
        if not wstpserver.exists():
            raise ServiceError(f"wstpserver path does not exist: {wstpserver}")
        return self._install(wstpserver, kernel)

    def uninstall(self) -> str:
        raise NotImplementedError

    def status(self) -> ServiceStatus:
        raise NotImplementedError

    def start(self) -> str:
        raise NotImplementedError

    def stop(self) -> str:
        raise NotImplementedError

    def restart(self) -> str:
        self.stop()
        return self.start()

    def kernel_process_count(self) -> int | None:
        return None

    def _install(self, wstpserver_bin: Path, kernel_bin: Path) -> str:
        raise NotImplementedError

    def _detect_kernel(self) -> Path | None:
        kernel = _kernel_from_wolframscript()
        if kernel:
            return kernel
        return _first_existing(self.kernel_globs())

    def _detect_wstpserver(self) -> Path | None:
        return _first_existing(self.wstpserver_globs())

    def _find_wstpserver_from_kernel(self, kernel: Path | None) -> Path | None:
        if not kernel:
            return None
        current = kernel.parent
        binary = "wstpserver.exe" if platform.system() == "Windows" else "wstpserver"
        for _ in range(8):
            candidate = current / "SystemFiles" / "Links" / "WSTPServer" / binary
            if candidate.exists():
                return candidate
            if current.parent == current:
                break
            current = current.parent
        return None

    def kernel_globs(self) -> tuple[str, ...]:
        return ()

    def wstpserver_globs(self) -> tuple[str, ...]:
        return ()

    def _run(self, command: Iterable[str], *, check: bool = True, timeout: int = 30) -> CommandResult:
        command_tuple = tuple(str(part) for part in command)
        completed = subprocess.run(
            command_tuple,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        result = CommandResult(command_tuple, completed.returncode, completed.stdout, completed.stderr)
        if check and completed.returncode != 0:
            raise ServiceError(result.output or f"Command failed: {' '.join(command_tuple)}")
        return result


class LinuxServiceManager(BaseServiceManager):
    name = "linux"

    def paths(self) -> ServicePaths:
        home = Path.home()
        return ServicePaths(
            config_file=home / ".config" / "wolfram-pool" / "wstpserver.conf",
            log_file=home / ".local" / "share" / "wolfram-pool" / "wstpserver.log",
            service_file=home / ".config" / "systemd" / "user" / SERVICE_NAME,
        )

    def kernel_globs(self) -> tuple[str, ...]:
        home = str(Path.home())
        return (
            f"{home}/Wolfram/Wolfram/*/Executables/WolframKernel",
            "/usr/local/Wolfram/*/Executables/WolframKernel",
            "/opt/Wolfram/*/Executables/WolframKernel",
        )

    def wstpserver_globs(self) -> tuple[str, ...]:
        home = str(Path.home())
        return (
            f"{home}/Wolfram/Wolfram/*/SystemFiles/Links/WSTPServer/wstpserver",
            "/usr/local/Wolfram/*/SystemFiles/Links/WSTPServer/wstpserver",
            "/opt/Wolfram/*/SystemFiles/Links/WSTPServer/wstpserver",
        )

    def _install(self, wstpserver_bin: Path, kernel_bin: Path) -> str:
        paths = self.paths()
        paths.config_file.parent.mkdir(parents=True, exist_ok=True)
        paths.log_file.parent.mkdir(parents=True, exist_ok=True)
        assert paths.service_file is not None
        paths.service_file.parent.mkdir(parents=True, exist_ok=True)
        created_config = ensure_config(paths.config_file, str(kernel_bin))
        paths.service_file.write_text(_systemd_unit(wstpserver_bin, paths.config_file, paths.log_file), encoding="utf-8")
        self._run(("systemctl", "--user", "daemon-reload"))
        self._run(("systemctl", "--user", "enable", "--now", SERVICE_NAME))
        if _command_exists("loginctl"):
            self._run(("loginctl", "enable-linger", os.environ.get("USER", "")), check=False)
        config_message = "Created config" if created_config else "Kept existing config"
        return f"{config_message}: {paths.config_file}\nInstalled service: {paths.service_file}"

    def uninstall(self) -> str:
        paths = self.paths()
        self._run(("systemctl", "--user", "disable", "--now", SERVICE_NAME), check=False)
        if paths.service_file:
            paths.service_file.unlink(missing_ok=True)
        self._run(("systemctl", "--user", "daemon-reload"), check=False)
        return "Removed systemd user service. Config and logs were left in place."

    def status(self) -> ServiceStatus:
        paths = self.paths()
        installed = bool(paths.service_file and paths.service_file.exists())
        active = self._run(("systemctl", "--user", "is-active", SERVICE_NAME), check=False)
        enabled = self._run(("systemctl", "--user", "is-enabled", SERVICE_NAME), check=False)
        running = active.stdout.strip() == "active"
        enabled_value = enabled.stdout.strip() == "enabled" if installed else False
        detail = active.stdout.strip() or active.stderr.strip() or "unknown"
        return ServiceStatus(installed, running, enabled_value, detail, self.kernel_process_count())

    def start(self) -> str:
        self._run(("systemctl", "--user", "start", SERVICE_NAME))
        return "Started systemd user service."

    def stop(self) -> str:
        self._run(("systemctl", "--user", "stop", SERVICE_NAME))
        return "Stopped systemd user service."

    def restart(self) -> str:
        self._run(("systemctl", "--user", "restart", SERVICE_NAME))
        return "Restarted systemd user service."

    def kernel_process_count(self) -> int | None:
        result = self._run(("pgrep", "-fc", "WolframKernel"), check=False)
        return _parse_count(result.stdout)


class MacOSServiceManager(BaseServiceManager):
    name = "macos"

    def paths(self) -> ServicePaths:
        home = Path.home()
        return ServicePaths(
            config_file=home / "Library" / "Application Support" / "wolfram-pool" / "wstpserver.conf",
            log_file=home / "Library" / "Logs" / "wolfram-pool" / "wstpserver.log",
            service_file=home / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist",
        )

    def kernel_globs(self) -> tuple[str, ...]:
        return (
            "/Applications/Wolfram*.app/Contents/MacOS/WolframKernel",
            "/Applications/Mathematica*.app/Contents/MacOS/WolframKernel",
        )

    def wstpserver_globs(self) -> tuple[str, ...]:
        return (
            "/Applications/Wolfram*.app/Contents/SystemFiles/Links/WSTPServer/wstpserver",
            "/Applications/Mathematica*.app/Contents/SystemFiles/Links/WSTPServer/wstpserver",
        )

    def _install(self, wstpserver_bin: Path, kernel_bin: Path) -> str:
        paths = self.paths()
        paths.config_file.parent.mkdir(parents=True, exist_ok=True)
        paths.log_file.parent.mkdir(parents=True, exist_ok=True)
        assert paths.service_file is not None
        paths.service_file.parent.mkdir(parents=True, exist_ok=True)
        created_config = ensure_config(paths.config_file, str(kernel_bin))
        _write_launchd_plist(paths.service_file, wstpserver_bin, paths.config_file, paths.log_file)
        self._run(("launchctl", "unload", "-w", str(paths.service_file)), check=False)
        self._run(("launchctl", "load", "-w", str(paths.service_file)))
        config_message = "Created config" if created_config else "Kept existing config"
        return f"{config_message}: {paths.config_file}\nInstalled LaunchAgent: {paths.service_file}"

    def uninstall(self) -> str:
        paths = self.paths()
        if paths.service_file:
            self._run(("launchctl", "unload", "-w", str(paths.service_file)), check=False)
            paths.service_file.unlink(missing_ok=True)
        return "Removed launchd agent. Config and logs were left in place."

    def status(self) -> ServiceStatus:
        paths = self.paths()
        installed = bool(paths.service_file and paths.service_file.exists())
        result = self._run(("launchctl", "list", LAUNCHD_LABEL), check=False)
        running = result.returncode == 0 and '"PID"' in result.stdout
        enabled = installed
        detail = "loaded" if result.returncode == 0 else "not loaded"
        return ServiceStatus(installed, running, enabled, detail, self.kernel_process_count())

    def start(self) -> str:
        paths = self.paths()
        if not paths.service_file or not paths.service_file.exists():
            raise ServiceError("LaunchAgent is not installed.")
        self._run(("launchctl", "load", "-w", str(paths.service_file)), check=False)
        self._run(("launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"), check=False)
        return "Started launchd agent."

    def stop(self) -> str:
        paths = self.paths()
        if paths.service_file:
            self._run(("launchctl", "unload", "-w", str(paths.service_file)), check=False)
        return "Stopped launchd agent."

    def restart(self) -> str:
        self.stop()
        return self.start()

    def kernel_process_count(self) -> int | None:
        result = self._run(("pgrep", "-fc", "WolframKernel"), check=False)
        return _parse_count(result.stdout)


class WindowsServiceManager(BaseServiceManager):
    name = "windows"

    def paths(self) -> ServicePaths:
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        local_appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return ServicePaths(
            config_file=appdata / "wolfram-pool" / "wstpserver.conf",
            log_file=local_appdata / "wolfram-pool" / "logs" / "wstpserver.log",
            service_file=None,
        )

    def kernel_globs(self) -> tuple[str, ...]:
        roots = _windows_program_roots()
        patterns: list[str] = []
        for root in roots:
            patterns.extend(
                (
                    str(root / "Wolfram Research" / "*" / "WolframKernel.exe"),
                    str(root / "Wolfram Research" / "*" / "wolfram.exe"),
                )
            )
        return tuple(patterns)

    def wstpserver_globs(self) -> tuple[str, ...]:
        roots = _windows_program_roots()
        return tuple(str(root / "Wolfram Research" / "*" / "SystemFiles" / "Links" / "WSTPServer" / "wstpserver.exe") for root in roots)

    def _install(self, wstpserver_bin: Path, kernel_bin: Path) -> str:
        paths = self.paths()
        paths.config_file.parent.mkdir(parents=True, exist_ok=True)
        paths.log_file.parent.mkdir(parents=True, exist_ok=True)
        created_config = ensure_config(paths.config_file, str(kernel_bin))
        script = f"""
$Action = New-ScheduledTaskAction -Execute {_ps_quote(str(wstpserver_bin))} -Argument {_ps_quote(f'-p {DEFAULT_PORT} -i {DEFAULT_HOST} -c "{paths.config_file}" -l 1 -f "{paths.log_file}"')}
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Unregister-ScheduledTask -TaskName {_ps_quote(WINDOWS_TASK_NAME)} -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName {_ps_quote(WINDOWS_TASK_NAME)} -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Wolfram Kernel Pool (WSTPServer)' | Out-Null
Start-ScheduledTask -TaskName {_ps_quote(WINDOWS_TASK_NAME)}
"""
        self._powershell(script)
        config_message = "Created config" if created_config else "Kept existing config"
        return f"{config_message}: {paths.config_file}\nInstalled scheduled task: {WINDOWS_TASK_NAME}"

    def uninstall(self) -> str:
        self._powershell(f"""
Stop-ScheduledTask -TaskName {_ps_quote(WINDOWS_TASK_NAME)} -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName {_ps_quote(WINDOWS_TASK_NAME)} -Confirm:$false -ErrorAction SilentlyContinue
""", check=False)
        return "Removed scheduled task. Config and logs were left in place."

    def status(self) -> ServiceStatus:
        script = f"""
$task = Get-ScheduledTask -TaskName {_ps_quote(WINDOWS_TASK_NAME)} -ErrorAction SilentlyContinue
if ($null -eq $task) {{ 'NOT_INSTALLED'; exit 0 }}
$info = Get-ScheduledTaskInfo -TaskName {_ps_quote(WINDOWS_TASK_NAME)} -ErrorAction SilentlyContinue
'INSTALLED'
'State=' + $task.State
if ($info) {{ 'LastRunTime=' + $info.LastRunTime; 'LastTaskResult=' + $info.LastTaskResult }}
"""
        result = self._powershell(script, check=False)
        output = result.stdout
        installed = "INSTALLED" in output
        state_match = re.search(r"State=(.+)", output)
        state = state_match.group(1).strip() if state_match else "Unknown"
        return ServiceStatus(installed, state.lower() == "running", installed, state, self.kernel_process_count())

    def start(self) -> str:
        self._powershell(f"Start-ScheduledTask -TaskName {_ps_quote(WINDOWS_TASK_NAME)}")
        return "Started scheduled task."

    def stop(self) -> str:
        self._powershell(f"Stop-ScheduledTask -TaskName {_ps_quote(WINDOWS_TASK_NAME)}")
        return "Stopped scheduled task."

    def restart(self) -> str:
        self.stop()
        return self.start()

    def kernel_process_count(self) -> int | None:
        result = self._powershell("(Get-Process WolframKernel,wolfram -ErrorAction SilentlyContinue).Count", check=False)
        return _parse_count(result.stdout)

    def _powershell(self, script: str, *, check: bool = True) -> CommandResult:
        executable = "powershell.exe"
        if _command_exists("pwsh.exe"):
            executable = "pwsh.exe"
        return self._run((executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script), check=check)


class UnsupportedServiceManager(BaseServiceManager):
    name = "unsupported"

    def paths(self) -> ServicePaths:
        return ServicePaths(Path.home() / "wstpserver.conf", Path.home() / "wstpserver.log", None)

    def status(self) -> ServiceStatus:
        return ServiceStatus(False, False, False, f"Unsupported platform: {platform.system()}")

    def _install(self, wstpserver_bin: Path, kernel_bin: Path) -> str:
        raise ServiceError(f"Unsupported platform: {platform.system()}")

    def uninstall(self) -> str:
        raise ServiceError(f"Unsupported platform: {platform.system()}")

    def start(self) -> str:
        raise ServiceError(f"Unsupported platform: {platform.system()}")

    def stop(self) -> str:
        raise ServiceError(f"Unsupported platform: {platform.system()}")


def get_service_manager() -> BaseServiceManager:
    system = platform.system()
    if system == "Linux":
        return LinuxServiceManager()
    if system == "Darwin":
        return MacOSServiceManager()
    if system == "Windows":
        return WindowsServiceManager()
    return UnsupportedServiceManager()


def _kernel_from_wolframscript() -> Path | None:
    command = "wolframscript.exe" if platform.system() == "Windows" else "wolframscript"
    if not _command_exists(command):
        return None
    try:
        completed = subprocess.run((command, "-showkernels"), capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = [line.strip().strip('"') for line in completed.stdout.splitlines()]
    for index, line in enumerate(lines):
        if "best WolframKernel location" in line:
            for candidate in lines[index + 1 :]:
                if candidate:
                    path = Path(candidate)
                    if path.exists():
                        return path
    for line in lines:
        if "WolframKernel" in line or line.endswith("wolfram.exe"):
            path = Path(line)
            if path.exists():
                return path
    return None


def _first_existing(patterns: Iterable[str]) -> Path | None:
    for pattern in patterns:
        for match in sorted(glob.glob(pattern)):
            path = Path(match)
            if path.exists():
                return path
    return None


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _systemd_unit(wstpserver_bin: Path, config_file: Path, log_file: Path) -> str:
    return f"""[Unit]
Description=Wolfram Kernel Pool (WSTPServer)
After=network.target

[Service]
ExecStart={_systemd_quote(wstpserver_bin)} -p {DEFAULT_PORT} -i {DEFAULT_HOST} -c {_systemd_quote(config_file)} -l 1 -f {_systemd_quote(log_file)}
Restart=on-failure

[Install]
WantedBy=default.target
"""


def _systemd_quote(path: Path) -> str:
    text = str(path)
    if not re.search(r"\s", text):
        return text
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _write_launchd_plist(path: Path, wstpserver_bin: Path, config_file: Path, log_file: Path) -> None:
    payload = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [
            str(wstpserver_bin),
            "-p",
            str(DEFAULT_PORT),
            "-i",
            DEFAULT_HOST,
            "-c",
            str(config_file),
            "-l",
            "1",
            "-f",
            str(log_file),
        ],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "StandardOutPath": str(log_file),
        "StandardErrorPath": str(log_file),
    }
    with path.open("wb") as file:
        plistlib.dump(payload, file)


def _windows_program_roots() -> tuple[Path, ...]:
    roots = []
    for key in ("ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(key)
        if value:
            roots.append(Path(value))
    return tuple(dict.fromkeys(roots))


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _parse_count(value: str) -> int | None:
    value = value.strip()
    if not value:
        return 0
    try:
        return int(value.splitlines()[-1].strip())
    except ValueError:
        return None
