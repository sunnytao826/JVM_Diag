Example GCeasy-style JSON (abbreviated):

```json
{
  "isProblem": false,
  "fatals": [],
  "warnings": [
    "In several GC events, 'real' time took more than 'usr' + 'sys' time."
  ],
  "gcKPI": {
    "throughputPercentage": 99.5,
    "averagePauseTime": 190,
    "maxPauseTime": 700
  }
}
```

When interpreting a GC report:
1. State whether the collector matches the JVM flags (G1, ZGC, Parallel, etc.).
2. Call out throughput, max pause, allocation/promotion rates, and heap peak.
3. Explain `real > usr + sys` as CPU throttle, noisy neighbors, or slow GC-log I/O — not as a GC algorithm failure by itself.
4. Give concrete JVM and container (CPU/memory request/limit) changes. Do not invent metrics that the tool did not return.
