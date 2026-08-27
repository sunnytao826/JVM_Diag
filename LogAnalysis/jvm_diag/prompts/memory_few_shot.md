MAT reports typically combine three views:

- Problem Suspects: largest retained-heap owners and leak suspects
- Top Consumers: biggest objects / dominator classes
- Class Histogram: instance counts and shallow/retained heap by class

Write the analysis in that order:
1. Name the leak suspects and retained heap share.
2. List the dominant retained types (collections, byte[], framework objects).
3. Flag abnormal instance counts versus a typical request or cache size.
4. Infer a plausible GC-root path (thread pool, ThreadLocal, static cache, unclosed cursor).
5. Give code-level actions (pagination, `ThreadLocal.remove()`, close resources). Never invent class names that are not in the tool output.
