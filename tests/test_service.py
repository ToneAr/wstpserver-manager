from __future__ import annotations

from types import SimpleNamespace

from wolfram_pool_tray.service import KernelProcess, _unix_descendant_kernel_processes


def _process(command: str) -> KernelProcess:
    return KernelProcess(
        pid=1,
        parent_pid=None,
        cpu_percent=None,
        memory_bytes=None,
        executable="WolframKernel",
        command=command,
    )


def test_is_subkernel_true_when_flag_present():
    process = _process("WolframKernel -subkernel -wstp")
    assert process.is_subkernel is True


def test_is_subkernel_false_when_flag_absent():
    process = _process("WolframKernel -wstp")
    assert process.is_subkernel is False


def test_is_subkernel_false_for_substring_match():
    # Must be a distinct token, not a substring of some other flag.
    process = _process("WolframKernel -subkernelish")
    assert process.is_subkernel is False


def test_is_subkernel_false_for_empty_command():
    process = _process("")
    assert process.is_subkernel is False


def test_unix_descendant_kernel_processes_excludes_defunct_kernels():
    output = """
      10     1  0.0  2048 wstpserver     wstpserver
      11    10  0.0     0 WolframKernel  [WolframKernel] <defunct>
      12    10  1.5  4096 WolframKernel  WolframKernel -wstp
    """

    def run(_command, *, check):
        return SimpleNamespace(stdout=output)

    processes = _unix_descendant_kernel_processes(10, run)

    assert [process.pid for process in processes] == [12]
