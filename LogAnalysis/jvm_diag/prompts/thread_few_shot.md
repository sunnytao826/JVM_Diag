Example hybrid thread-dump JSON (abbreviated):

```json
{
  "tda_analysis": {
    "summary": [{"threadCount": 197, "deadlockCount": 0}],
    "deadlocks": ["No deadlocks found"]
  },
  "has_lock_contention": false,
  "status": {"RUNNABLE": 62, "WAITING": 78, "TIMED_WAITING": 48},
  "hot_runnable": []
}
```

When interpreting:
1. Deadlocks and lock waiters first.
2. State histogram: high RUNNABLE may be CPU or blocking native I/O (`EPoll.wait`, socket read).
3. Use hot methods / long-running stacks to distinguish busy-wait from I/O wait.
4. Recommend `top -H` + `jstack` correlation only when CPU is actually high.
5. Do not claim a deadlock or leak unless the tool output shows one.
