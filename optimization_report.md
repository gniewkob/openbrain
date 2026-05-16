# Optimization Report: N+1 Query in Memory Export

## Problem
The `v1_export` endpoint in `unified/src/api/v1/memory.py` exhibited a classic N+1 query pattern. Before exporting memories, the code would iterate through the list of requested IDs and call `get_memory(session, memory_id)` for each one to perform validation and access control checks.

```python
    for memory_id in req.ids:
        mem = await get_memory(session, memory_id)
        if mem is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        # ... access control checks
```

For an export request with $N$ IDs, this resulted in $N$ separate database round-trips to fetch the `Memory` objects, followed by another query in `export_memories` to fetch them again for the actual export.

## Solution
The optimization involves:
1.  Implementing a batch retrieval function `get_memories_batch` that uses the SQLAlchemy `IN` operator to fetch all requested `Memory` objects in a single query.
2.  Refactoring the validation loop in `v1_export` to use this batch retrieval, reducing the number of database round-trips for validation from $O(N)$ to $O(1)$.

## Theoretical Performance Improvement
- **Before:** $N$ queries for validation + 1 query for export = $N + 1$ queries.
- **After:** 1 query for validation + 1 query for export = 2 queries.

For a large number of IDs (e.g., $N=100$), this reduces the database interaction from 101 round-trips to just 2. This significantly reduces latency, especially in environments where database round-trip time is non-negligible, and reduces the load on the database server.

## Correctness and Safety
- The optimized logic ensures that if any requested ID is missing, it still raises a 404 error, preserving existing behavior.
- Access control checks are still performed for every fetched memory record.
- The use of `IN` is safe and standard practice for batch retrieval.
