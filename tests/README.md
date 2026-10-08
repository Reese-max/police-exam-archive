The required Python gate also runs the original quiz page in Node with a pinned,
independent IndexedDB implementation. Install its single test dependency first:

```sh
npm ci --prefix tests --ignore-scripts
REQUIRE_NODE_FOR_TESTS=1 python -m pytest tests/ -q
```

`quiz_dom_harness.js` awaits the original page's transaction completion rather
than treating synchronous localStorage comparisons as cross-tab ownership.
The durability cases cover stale legacy renderer writes, simultaneous claims,
fresh answers accepted after the banner was offered, completion tombstones,
timer/answer overlap, corrupt records, aborted transactions, and failed cleanup
after a durable save (including the later no-recovery transition). Failed finish
keeps the original exam and clock until a retry commits the tombstone. These are Node
regressions; actual browser close/reopen durability needs browser verification.
