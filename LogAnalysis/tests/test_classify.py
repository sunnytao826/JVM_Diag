from jvm_diag.coordinator import SmartRootCoordinator


def test_classify_heap():
    assert SmartRootCoordinator.classify_by_filename("/tmp/app.hprof") == "memory"
    assert SmartRootCoordinator.classify_by_filename("dump.heapdump") == "memory"


def test_classify_gc():
    assert SmartRootCoordinator.classify_by_filename("./pod-gc.log") == "gc"
    assert SmartRootCoordinator.classify_by_filename("gc.log") == "gc"
    assert SmartRootCoordinator.classify_by_filename("application.log") is None


def test_classify_thread():
    assert SmartRootCoordinator.classify_by_filename("threaddump-1.tdump") == "thread"
    assert SmartRootCoordinator.classify_by_filename("app.jstack") == "thread"
    assert SmartRootCoordinator.classify_by_filename("notes.txt") is None
