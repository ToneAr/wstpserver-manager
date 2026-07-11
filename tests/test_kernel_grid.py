from __future__ import annotations

from PyQt6.QtCore import Qt

from wolfram_pool_tray.app import _sort_kernel_processes, _split_kernel_processes
from wolfram_pool_tray.service import KernelProcess


def _process(
    pid: int,
    command: str = "WolframKernel -wstp",
    parent_pid: int | None = 100,
    cpu_percent: float | None = None,
    memory_bytes: int | None = None,
    executable: str = "WolframKernel",
) -> KernelProcess:
    return KernelProcess(
        pid=pid,
        parent_pid=parent_pid,
        cpu_percent=cpu_percent,
        memory_bytes=memory_bytes,
        executable=executable,
        command=command,
    )


def test_split_separates_main_and_subkernels():
    main_proc = _process(1, "WolframKernel -wstp")
    sub_proc = _process(2, "WolframKernel -subkernel -wstp")
    main, parallel = _split_kernel_processes((main_proc, sub_proc))
    assert main == (main_proc,)
    assert parallel == (sub_proc,)


def test_split_with_no_subkernels():
    main_proc = _process(1)
    main, parallel = _split_kernel_processes((main_proc,))
    assert main == (main_proc,)
    assert parallel == ()


def test_sort_by_pid_ascending_and_descending():
    p1 = _process(3)
    p2 = _process(1)
    p3 = _process(2)
    ascending = _sort_kernel_processes((p1, p2, p3), column=0, order=Qt.SortOrder.AscendingOrder)
    assert [p.pid for p in ascending] == [1, 2, 3]
    descending = _sort_kernel_processes((p1, p2, p3), column=0, order=Qt.SortOrder.DescendingOrder)
    assert [p.pid for p in descending] == [3, 2, 1]


def test_sort_by_parent_pid_puts_none_last_in_either_direction():
    p1 = _process(1, parent_pid=None)
    p2 = _process(2, parent_pid=5)
    ascending = _sort_kernel_processes((p1, p2), column=1, order=Qt.SortOrder.AscendingOrder)
    assert [p.pid for p in ascending] == [2, 1]
    descending = _sort_kernel_processes((p1, p2), column=1, order=Qt.SortOrder.DescendingOrder)
    assert [p.pid for p in descending] == [2, 1]


def test_sort_by_executable_is_case_insensitive():
    p1 = _process(1, executable="wolframkernel")
    p2 = _process(2, executable="AlphaKernel")
    ascending = _sort_kernel_processes((p1, p2), column=4, order=Qt.SortOrder.AscendingOrder)
    assert [p.pid for p in ascending] == [2, 1]


def test_sort_unknown_column_returns_unchanged_order():
    p1 = _process(1)
    p2 = _process(2)
    result = _sort_kernel_processes((p1, p2), column=6, order=Qt.SortOrder.AscendingOrder)
    assert result == (p1, p2)
