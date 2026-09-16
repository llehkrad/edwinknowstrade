"""
Compatibility shim for ib_insync on Python 3.12+ (including 3.14).

ib_insync's `eventkit` dependency calls asyncio.get_event_loop() at import
time, relying on old implicit-loop-creation behavior that newer Python
versions removed -- this raises "RuntimeError: There is no current event
loop in thread 'MainThread'" before ib_insync even finishes importing.

Call ensure_event_loop() before `import ib_insync` / `from ib_insync import
...` in any entry point to work around it. ib_insync itself (last released
2023) appears unmaintained -- if this shim ever stops working, switch to
the actively maintained `ib_async` fork instead (same API surface).
"""
import asyncio


def ensure_event_loop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
