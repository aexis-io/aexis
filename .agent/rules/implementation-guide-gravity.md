---
trigger: always_on
---

**PRODUCTION CODE REQUIREMENTS**

**Code Quality Standards:**
- Production-grade only: battle-tested patterns, robust error handling, complete edge case coverage
- Name things for what they DO, not architectural patterns they follow
- Real-world resilience: network failures, race conditions, resource exhaustion, malformed inputs


**Required Elements:**
- Explicit error handling with recovery strategies
- Input validation with specific error messages
- Resource cleanup (connections, files, locks)
- Logging at decision points, not verbose trace logs
- Performance considerations documented for O(n²)+ operations
- Concurrency safety where applicable

**Documentation & Verification:**
- ALWAYS check project docs/specs before implementing features
- Verify method/API existence before calling - check documentation or codebase
- If uncertain about a method signature or availability, explicitly verify or flag uncertainty
- Align implementation with documented project requirements and architecture decisions

**Forbidden:**
- Placeholder comments like "// TODO: implement", "// Add error handling"
- Generic catch-all error handlers
- Theoretical optimization without profiling data
- Over-engineered "future-proofing"
- Calling methods without verifying they exist in the actual API/codebase

**Verification Checklist:**
- Does this code handle the failure case?
- Can this run in production without modifications?
- Are resource limits considered?
- Is the naming self-documenting?
- Have I verified this method/API actually exists?
- Does this align with documented project specifications?

