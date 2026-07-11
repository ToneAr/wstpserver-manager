# WSTPServer Manager

Persistent Wolfram Language Kernel Server Service

Runs [WSTPServer](https://reference.wolfram.com/language/tutorial/IntroductionToWSTPServer.html)
as a background service that keeps a pool of warm Wolfram kernels listening
on `localhost:31415`, restarting automatically if it crashes.

## Layout

- `common/wstpserver.conf.json.template` — shared WSTPServer config template
  (JSON). The install script fills in the local kernel path and drops the
  result next to the platform-specific config directory.
- `common/detect-wolfram.sh` — shared kernel/wstpserver detection, sourced by
  the Linux and macOS install scripts.
- `linux/` — Linux, via a `systemd --user` service.
- `macos/` — macOS, via a per-user `launchd` agent.
- `windows/` — Windows, via a Scheduled Task (starts at logon, restarts on
  failure).
- `src/wolfram_pool_tray/` — PyQt6 tray application for installing,
  starting/stopping, and editing the WSTPServer kernel pool config.
- `packaging/pyinstaller/` — PyInstaller entry point/spec for native desktop
  bundles.
- `packaging/installers/` — platform installer builders that install the app
  and then install the platform WSTPServer service.

## Install

Each platform has an `install.sh` (or `install.ps1`) that auto-detects the
Wolfram installation, writes a config file (if one doesn't already exist),
generates the platform service definition, and starts the service.

Detection first runs `wolframscript -showkernels` to find the kernel path,
then derives the `wstpserver` binary path by walking up from the kernel
directory looking for `SystemFiles/Links/WSTPServer/wstpserver`. If
`wolframscript` isn't on `PATH`, the scripts fall back to scanning common
install locations.

```sh
# Linux
./linux/install.sh

# macOS
./macos/install.sh

# Windows (PowerShell)
.\windows\install.ps1
```

If auto-detection fails, point the script at your install directly:

```sh
# Linux / macOS
WSTPSERVER_BIN=/path/to/wstpserver KERNEL_BIN=/path/to/WolframKernel ./linux/install.sh

# Windows
.\windows\install.ps1 -WstpServerBin 'C:\path\to\wstpserver.exe' -KernelBin 'C:\path\to\wolfram.exe'
```

## Tray application

The PyQt6 tray application provides a small desktop interface for:

- auto-detecting `wstpserver` and `WolframKernel`;
- installing/updating the platform service (`systemd --user`, `launchd`, or a
  Windows Scheduled Task);
- starting, stopping, restarting, and uninstalling the service;
- editing the first configured kernel pool's `KernelPath`,
  `MinimumKernelNumber`, `MaximumKernelNumber`, and `KeepAlive` settings;
- editing the full `wstpserver.conf` from the main window or tray menu, including
  documented root settings and any kernel pool's documented settings;
- choosing another `wstpserver.conf` file to edit with the same GUI;
- opening the generated config/log directories.

Install and run it from source using a virtual environment. This avoids
PEP 668 `externally-managed-environment` errors on distributions such as Arch
Linux:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
wstpserver-tray
```

Alternatively, install it as an isolated desktop app with `pipx`:

```sh
pipx install .
wstpserver-tray
```

For local packaging with PyInstaller, use the same virtual environment:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[package]"
python -m PyInstaller --noconfirm packaging/pyinstaller/wstpserver-tray.spec
```

The frozen app also exposes service-install hooks for installers and scripted
setup:

```sh
WSTPServerManager --install-service
WSTPServerManager --service-status
WSTPServerManager --uninstall-service
WSTPServerManager --start-hidden
```

Build an installer after the PyInstaller bundle is created:

```sh
# Linux: creates dist/installers/WSTPServerManager-<version>-linux-x86_64.run
bash packaging/installers/linux/build-installer.sh

# macOS: creates dist/installers/WSTPServerManager-<version>-macos.pkg
bash packaging/installers/macos/build-pkg.sh

# Windows: creates dist/installers/WSTPServerManager-<version>-windows-x64-setup.exe
powershell -ExecutionPolicy Bypass -File .\packaging\installers\windows\build-installer.ps1
```

The Linux installer is a user-level `.run` installer. It installs the app under
`~/.local/opt/WSTPServerManager`, adds a `wstpserver-manager` launcher, writes
desktop and XDG autostart entries, and installs the `systemd --user` service.
The macOS `.pkg` installs the app into `/Applications`, installs the per-user
WSTPServer LaunchAgent, and writes a per-user LaunchAgent that starts the tray
app hidden at login. The Windows installer uses Inno Setup, installs into the
current user's LocalAppData programs directory, registers the Scheduled Task,
and registers the tray app in the current user's Startup Run key.

For Linux and macOS releases, you can also use the bootstrap installer script:

```sh
curl -fsSL https://github.com/ToneAr/wstpserver-manager/releases/latest/download/install.sh | sh
```

Linux installer options can be passed after `sh -s --`:

```sh
curl -fsSL https://github.com/ToneAr/wstpserver-manager/releases/latest/download/install.sh | sh -s -- --skip-service
```

To install a specific release tag:

```sh
curl -fsSL https://github.com/ToneAr/wstpserver-manager/releases/latest/download/install.sh | VERSION=v0.2.1 sh
```

The GitHub Actions workflow in `.github/workflows/build-tray.yml` builds these
installers on `ubuntu-latest`, `macos-latest`, and `windows-latest` and uploads
`WSTPServerManager-*` artifacts.

## Uninstall

```sh
./linux/uninstall.sh       # add --purge to also remove config/logs
./macos/uninstall.sh       # add --purge to also remove config/logs
.\windows\uninstall.ps1    # add -Purge to also remove config/logs
```

## Config

The generated `wstpserver.conf` is plain JSON (see
`common/wstpserver.conf.json.template`). Use **Edit Full Config…** in the main
window or **Configuration → Edit Service Config…** in the tray menu to edit the
documented WSTPServer root keys and per-pool keys with the GUI. The tray menu's
**Configuration → Edit Other Config File…** action can edit another
`wstpserver.conf`, such as one used from a current working directory or passed
to `wstpserver --configuration-file`.

Restart WSTPServer after editing for changes to take effect.
