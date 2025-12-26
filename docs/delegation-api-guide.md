# Delegation API Guide

## Quick Start

### Basic Delegation

```python
# Parent agent delegates a focused task
result = delegate_task(
    prompt="Run pytest on tests/test_auth.py and report results",
    timeout=120
)
```

### With Custom Model

```python
# Use a different model for the child agent
result = delegate_task(
    prompt="Analyze performance bottlenecks in src/api/",
    timeout=300,
    model="gpt-4"  # Override parent's model
)
```

## Delegation Tool API

### Function Signature

```python
async def delegate_task(
    prompt: str,
    timeout: float = 300.0,
    model: Optional[str] = None
) -> str
```

### Parameters

**`prompt`** (required)
- Type: `str`
- Description: Self-contained task description for child agent
- Best practices:
  - Include all necessary context
  - Specify file paths explicitly
  - Define success criteria
  - Provide clear instructions

**`timeout`** (optional)
- Type: `float`
- Default: `300.0` (5 minutes)
- Description: Maximum execution time in seconds
- Recommendations:
  - Quick tasks: 60-120s
  - Medium tasks: 180-300s
  - Complex tasks: 300-600s
  - Long-running: 600s+

**`model`** (optional)
- Type: `str`
- Default: Inherits parent's model
- Description: Override LLM model for child
- Use cases:
  - Use faster model for simple tasks
  - Use stronger model for complex analysis
  - Cost optimization strategies

### Return Value

**Success Response:**
```xml
<Agent's text response>

<execution_summary>
  <session_id>child-abc123</session_id>
  <status>completed</status>
  <duration>45.23s</duration>
  <success_rate>95%</success_rate>

  <files>
    <read count="3">src/auth.py, tests/test_auth.py, README.md</read>
    <modified count="2">src/auth.py, tests/test_auth.py</modified>
  </files>

  <tools total="8">
    read_file: 3x
    edit_file: 2x
    bash: 2x
    grep: 1x
  </tools>

  <errors count="1">
    • bash: npm test failed with exit code 1
  </errors>
</execution_summary>
```

**Failure Response:**
```
Child agent failed: <error message>

Category: <failure_category>
Duration: <duration>s
Retryable: <Yes|No>

Work completed before failure:
  ✓ <completed step 1>
  ✓ <completed step 2>

Files modified: <comma-separated list>

Blocked on: <specific blocker>

Suggested recovery actions:
  • <action 1>
  • <action 2>

<task_metadata>
  <session_id>child-abc123</session_id>
  <status>failed</status>
  <failure_category>timeout|tool_error|missing_context|invalid_task|partial</failure_category>
  <retryable>true|false</retryable>
</task_metadata>
```

## Execution Summary Format

### XML Schema

The `<execution_summary>` block contains structured data about the child's execution:

**Session Information:**
- `<session_id>`: Unique identifier for child session
- `<status>`: "completed" or "failed"
- `<duration>`: Execution time in seconds

**Performance Metrics:**
- `<success_rate>`: Percentage of successful tool calls

**File Operations:**
```xml
<files>
  <read count="N">file1, file2, ...</read>
  <modified count="M">file1, file2, ...</modified>
</files>
```

**Tool Usage:**
```xml
<tools total="N">
  tool_name: Nx
  another_tool: Mx
</tools>
```

**Errors (if any):**
```xml
<errors count="N">
  • tool_name: error message
</errors>
```

### Parsing Example

```python
import xml.etree.ElementTree as ET

result = delegate_task(prompt="...")

# Check if successful
if "<status>completed</status>" in result:
    # Extract files modified
    if "<modified" in result:
        # Parse XML for detailed info
        summary_start = result.find("<execution_summary>")
        summary_end = result.find("</execution_summary>") + len("</execution_summary>")
        xml_str = result[summary_start:summary_end]
        root = ET.fromstring(xml_str)

        files_modified = root.find(".//files/modified").text
        success_rate = root.find(".//success_rate").text

        print(f"Modified: {files_modified}")
        print(f"Success rate: {success_rate}")
```

## Failure Handling

### Failure Categories

**TIMEOUT**
- **Cause**: Child exceeded timeout limit
- **Retryable**: Yes (if progress was made)
- **Recovery**: Increase timeout or break into subtasks

**MISSING_CONTEXT**
- **Cause**: Insufficient information in prompt
- **Retryable**: No (needs prompt improvement)
- **Recovery**: Provide more context, include file paths

**TOOL_ERROR**
- **Cause**: External tool/dependency failed
- **Retryable**: Yes (after fixing environment)
- **Recovery**: Install dependencies, fix permissions

**INVALID_TASK**
- **Cause**: Task impossible or unclear
- **Retryable**: No (needs task redefinition)
- **Recovery**: Clarify requirements, simplify task

**PARTIAL_SUCCESS**
- **Cause**: Some work done, hit blocker
- **Retryable**: Yes (may need different approach)
- **Recovery**: Complete remaining work, fix blocker

### Retry Strategy

```python
# Example: Intelligent retry logic
def delegate_with_retry(prompt: str, max_retries: int = 2):
    timeout = 300

    for attempt in range(max_retries):
        result = delegate_task(prompt=prompt, timeout=timeout)

        # Check for timeout with progress
        if "<failure_category>timeout</failure_category>" in result:
            if "<retryable>true</retryable>" in result:
                # Double timeout and retry
                timeout *= 2
                continue
            else:
                # No progress, break into subtasks
                break

        # Check for tool errors
        elif "<failure_category>tool_error</failure_category>" in result:
            if "<retryable>true</retryable>" in result:
                # Extract suggested actions and prompt user
                # Then retry
                continue

        # Success or non-retryable failure
        break

    return result
```

## Use Cases

### 1. Parallel Testing

```python
# Test multiple components simultaneously
backend_result = delegate_task(
    prompt="Run all tests in tests/backend/ and report failures",
    timeout=180
)

frontend_result = delegate_task(
    prompt="Run all tests in tests/frontend/ and report failures",
    timeout=180
)
```

### 2. Code Analysis

```python
# Deep analysis of specific module
result = delegate_task(
    prompt="""
    Analyze src/api/auth.py for:
    - Security vulnerabilities
    - Performance bottlenecks
    - Code quality issues
    - Missing error handling

    Provide specific line numbers and fix suggestions.
    """,
    timeout=240
)
```

### 3. Research Tasks

```python
# Gather information without modifying code
result = delegate_task(
    prompt="""
    Research the following:
    1. List all API endpoints in src/api/
    2. Document each endpoint's:
       - HTTP method
       - Parameters
       - Return type
       - Error handling
    3. Output results in markdown table
    """,
    timeout=300
)
```

### 4. Refactoring

```python
# Isolated refactoring task
result = delegate_task(
    prompt="""
    Refactor src/utils/validators.py:
    1. Extract common validation logic into helper functions
    2. Add type hints to all functions
    3. Update tests in tests/test_validators.py
    4. Run tests to ensure nothing broke
    """,
    timeout=400
)
```

### 5. Documentation Generation

```python
# Generate docs from code
result = delegate_task(
    prompt="""
    Generate API documentation for src/api/:
    1. Read all files in src/api/
    2. Extract function signatures and docstrings
    3. Create docs/api-reference.md with:
       - Function descriptions
       - Parameters
       - Return values
       - Usage examples
    """,
    timeout=300
)
```

## Best Practices

### ✅ DO: Provide Complete Context

```python
# Good: Self-contained with all needed info
delegate_task(
    prompt="""
    Test authentication in src/auth.py:
    1. Run: pytest tests/test_auth.py -v
    2. If failures, read the test file and implementation
    3. Fix any issues found
    4. Re-run tests until all pass
    5. Report what was fixed

    Database credentials are in .env.test
    """,
    timeout=300
)
```

### ❌ DON'T: Assume Parent Context

```python
# Bad: References parent's conversation
delegate_task(
    prompt="Fix the bug we discussed earlier in that file"
)
```

### ✅ DO: Set Appropriate Timeouts

```python
# Quick task - short timeout
delegate_task(
    prompt="Read src/config.py and count LOC",
    timeout=30
)

# Complex task - longer timeout
delegate_task(
    prompt="Refactor entire auth module with full test coverage",
    timeout=600
)
```

### ❌ DON'T: Over-Delegate Trivial Tasks

```python
# Bad: Overhead exceeds benefit
delegate_task(
    prompt="Read file.txt and tell me the first line",
    timeout=60
)

# Good: Just do it yourself
content = read_file("file.txt")
first_line = content.split('\n')[0]
```

### ✅ DO: Include Success Criteria

```python
# Good: Clear success definition
delegate_task(
    prompt="""
    Optimize query performance in src/db/queries.py:
    - Add database indexes where needed
    - Use query optimization techniques
    - Success: All queries < 100ms on test dataset
    - Run benchmarks to verify improvements
    """,
    timeout=400
)
```

### ✅ DO: Specify File Paths

```python
# Good: Explicit paths
delegate_task(
    prompt="Analyze files: src/auth.py, src/models/user.py, tests/test_auth.py"
)

# Bad: Vague references
delegate_task(
    prompt="Analyze the auth code"
)
```

## Limitations

### What Child Agents CANNOT Do

1. **Access Parent History**
   - Child only sees the delegation prompt
   - No access to previous conversation
   - Must be self-contained

2. **Create Todo Lists**
   - `todo` tool is restricted
   - Parent manages task planning

3. **Delegate Further**
   - No recursive delegation
   - Only parent → child, not child → grandchild

4. **Modify Parent State**
   - Child cannot affect parent's memory
   - Isolated execution environment

### Workarounds

**Need Parent Context?**
- Include relevant context in prompt
- Copy important information to prompt
- Reference specific file paths

**Need Todo Management?**
- Parent creates todos before delegation
- Child reports completed steps in response
- Parent updates todos based on child's report

**Need Nested Delegation?**
- Parent breaks work into multiple child tasks
- Sequential delegation: wait for child 1, then spawn child 2
- Parallel delegation: spawn multiple children at once

## Performance Tips

### Optimize Timeout Settings

```python
# Profile task complexity
task_complexity = {
    "read_only": 60,      # Just reading/analyzing
    "simple_edit": 120,   # Edit 1-2 files
    "moderate": 300,      # Edit multiple files + tests
    "complex": 600,       # Major refactoring
}

delegate_task(
    prompt=prompt,
    timeout=task_complexity[task_type]
)
```

### Use Appropriate Models

```python
# Simple tasks - faster/cheaper model
delegate_task(
    prompt="Count functions in src/utils.py",
    model="gpt-3.5-turbo",  # Cheaper
    timeout=30
)

# Complex tasks - stronger model
delegate_task(
    prompt="Refactor architecture with design patterns",
    model="gpt-4",  # Better reasoning
    timeout=600
)
```

### Batch Related Tasks

```python
# Instead of multiple delegations
delegate_task(prompt="Test module A")
delegate_task(prompt="Test module B")
delegate_task(prompt="Test module C")

# Better: Batch into one
delegate_task(
    prompt="""
    Test all modules:
    1. pytest tests/module_a/
    2. pytest tests/module_b/
    3. pytest tests/module_c/
    Report consolidated results
    """,
    timeout=300
)
```

## Error Handling Examples

### Handle Timeout Gracefully

```python
result = delegate_task(prompt="Large task", timeout=300)

if "<failure_category>timeout</failure_category>" in result:
    # Extract partial progress
    if "Files modified:" in result:
        # Parse modified files
        start = result.find("Files modified:") + len("Files modified:")
        end = result.find("\n", start)
        files = result[start:end].strip()

        print(f"Child modified {files} before timeout")

    # Retry with adjusted timeout
    if "<retryable>true</retryable>" in result:
        result = delegate_task(prompt="Large task", timeout=600)
```

### Handle Tool Errors

```python
result = delegate_task(prompt="Install and test")

if "<failure_category>tool_error</failure_category>" in result:
    # Extract error details
    if "<errors" in result:
        # Parse error section
        # Fix environment (install deps, etc.)
        # Retry
        result = delegate_task(prompt="Install and test", timeout=300)
```

## Advanced Patterns

### Conditional Delegation

```python
# Delegate based on conditions
files = glob("src/**/*.py")

if len(files) > 50:
    # Too many files - delegate analysis
    result = delegate_task(
        prompt=f"Analyze all {len(files)} Python files in src/",
        timeout=600
    )
else:
    # Few files - handle directly
    for file in files:
        content = read_file(file)
        # analyze...
```

### Progressive Refinement

```python
# First pass - quick analysis
result = delegate_task(
    prompt="Quick analysis of src/api/ - identify 3 biggest issues",
    timeout=120
)

# Second pass - detailed work on identified issues
if "<status>completed</status>" in result:
    issues = extract_issues(result)

    for issue in issues:
        delegate_task(
            prompt=f"Fix issue: {issue}",
            timeout=300
        )
```

### Result Aggregation

```python
# Delegate multiple analyses
results = []

for module in ["auth", "api", "database"]:
    result = delegate_task(
        prompt=f"Analyze src/{module}/ for security issues",
        timeout=180
    )
    results.append(result)

# Aggregate findings
all_issues = aggregate_security_findings(results)
```

## Debugging Delegation

### Enable Verbose Logging

```python
# Check session events
# Query: SELECT * FROM session_events WHERE session_id = 'parent-id'
# Shows: delegation_start, delegation_complete, delegation_timeout, delegation_error
```

### Inspect Child Session

```python
# After delegation, child session persists in database
# Can review conversation history, messages, and events
# Useful for understanding what child agent did
```

### Monitor Progress in Real-Time

Parent console displays live progress:
```
┌─ Delegated Task
│ Child agent started...
│ ▶ read_file          ← Tool started
│ ✓ read_file          ← Tool completed
│ ▶ bash
│ ✗ bash: Error       ← Tool failed
└─ Task completed
```

## FAQ

**Q: Can child agents delegate to other children?**
A: No, recursive delegation is not supported. Only parent agents can delegate.

**Q: Do child agents share parent's conversation history?**
A: No, child agents only receive the delegation prompt. Include all needed context in the prompt.

**Q: What happens if child times out?**
A: Child returns a structured failure report with partial progress, retry suggestions, and recovery actions.

**Q: Can I cancel a running delegation?**
A: Not currently supported. Set appropriate timeouts instead.

**Q: How do I know which files child modified?**
A: Parse the `<execution_summary>` → `<files>` → `<modified>` section in the response.

**Q: What's the maximum timeout?**
A: No hard limit, but recommended max is 600s (10 minutes). Longer tasks should be broken into subtasks.

**Q: Can child agents access environment variables?**
A: Yes, child agents inherit parent's environment.

**Q: How are errors reported?**
A: Errors appear in both the `<execution_summary>` → `<errors>` section and the failure report.
