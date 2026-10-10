"""Test backend stdout drain logic."""
import threading
import time
from io import StringIO


def test_drain_reads_from_passed_process():
    """Drain 从传入的 process.stdout 读取."""
    # Mock process with stdout
    class MockProcess:
        def __init__(self, lines):
            self.stdout = iter(lines)
    
    lines_out = []
    stop_event = threading.Event()
    
    # Import drain function
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.verify_credible_manual_trade_closure import _drain_backend
    
    process = MockProcess(["line1\n", "line2\n", "line3\n"])
    
    thread = threading.Thread(target=_drain_backend, args=(process, lines_out, stop_event))
    thread.start()
    thread.join(timeout=2)
    
    assert len(lines_out) == 3, f"Expected 3 lines, got {len(lines_out)}"
    assert lines_out[0] == "line1\n"
    assert lines_out[2] == "line3\n"


def test_drain_stops_on_event():
    """Drain 在 stop_event 设置后停止."""
    class MockProcess:
        def __init__(self):
            self.stdout = self._gen()
        
        def _gen(self):
            for i in range(100):
                yield f"line{i}\n"
                time.sleep(0.01)
    
    lines_out = []
    stop_event = threading.Event()
    
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.verify_credible_manual_trade_closure import _drain_backend
    
    process = MockProcess()
    
    thread = threading.Thread(target=_drain_backend, args=(process, lines_out, stop_event))
    thread.start()
    time.sleep(0.05)  # 让它读几行
    stop_event.set()
    thread.join(timeout=2)
    
    # 应该读了一些但不是全部
    assert 1 <= len(lines_out) < 100, f"Expected 1-99 lines, got {len(lines_out)}"
