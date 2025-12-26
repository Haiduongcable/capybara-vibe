# Failure Recovery Guide

## Overview

Phase 2 enhancement introduces intelligent failure recovery for child agent delegations. When child agents fail, the system provides structured failure reports with categorization, partial progress tracking, and actionable recovery guidance.

## Failure Categories

### TIMEOUT

**Description**: Child agent exceeded timeout limit

**Common Causes:**
- Task more complex than estimated
- Slow tool execution (network issues, large files)
- Agent stuck in reasoning loop

**Retry Decision:**
- ✅ Retry if progress was made (`tool_executions > 0`)
- ❌ Don't retry if no progress (likely invalid task)

**Recovery Actions:**
```python
# Suggested by system:
- "Retry with timeout=600s" (doubled from 300s)
- "Break task into smaller subtasks"
```

**Example:**
```
Child agent failed: Child timed out after 300s

Category: timeout
Duration: 300.0s
Retryable: Yes

Work completed before failure:
  ✓ Created 2 files
  ✓ Modified 1 file

Files modified: src/config.py, tests/test_config.py

Blocked on: Time limit insufficient

Suggested recovery actions:
  • Retry with timeout=600s
  • Break task into smaller subtasks
```

### MISSING_CONTEXT

**Description**: Insufficient information in delegation prompt

**Common Causes:**
- Prompt references parent's conversation history
- Missing file paths or configuration details
- Vague task description
- Assumes knowledge not provided

**Retry Decision:**
- ❌ Don't retry without improving prompt
- ✅ Retry after adding necessary context

**Recovery Actions:**
```python
# Suggested by system:
- "Include specific file paths in prompt"
- "Provide configuration details or credentials"
- "Add example of expected output"
```

**Example:**
```
Child agent failed: Cannot find 'the auth file' mentioned in prompt

Category: missing_context
Duration: 15.3s
Retryable: No

Work completed before failure:
  None

Files modified: none

Blocked on: Unknown file reference

Suggested recovery actions:
  • Include specific file paths in prompt
  • Provide full context (child has no access to parent history)
```

### TOOL_ERROR

**Description**: External tool or dependency failed

**Common Causes:**
- Missing dependencies (npm packages, Python modules)
- File permission issues
- Command not found
- Network failures
- Database connection errors

**Retry Decision:**
- ✅ Retry after fixing environment
- ❌ Don't retry if tool fundamentally unavailable

**Recovery Actions:**
```python
# Suggested by system:
- "Check file permissions"
- "Install missing dependencies: npm install"
- "Verify command exists: which <command>"
```

**Example:**
```
Child agent failed: ModuleNotFoundError: No module named 'pytest'

Category: tool_error
Duration: 8.7s
Retryable: Yes

Work completed before failure:
  None

Files modified: none

Blocked on: ModuleNotFoundError: No module named 'pytest'

Suggested recovery actions:
  • Install missing dependencies
  • Run: pip install pytest
  • Verify installation: pytest --version
```

### INVALID_TASK

**Description**: Task is impossible, unclear, or contradictory

**Common Causes:**
- Contradictory requirements
- Physically impossible operations
- Unclear success criteria
- Task outside agent capabilities

**Retry Decision:**
- ❌ Don't retry without redefining task
- ✅ Retry after clarifying requirements

**Recovery Actions:**
```python
# Suggested by system:
- "Clarify task requirements"
- "Break into simpler, well-defined tasks"
- "Provide specific success criteria"
```

**Example:**
```
Child agent failed: Cannot both 'preserve all code' and 'delete entire module'

Category: invalid_task
Duration: 12.1s
Retryable: No

Work completed before failure:
  None

Files modified: none

Blocked on: Contradictory requirements in prompt

Suggested recovery actions:
  • Clarify task requirements
  • Remove contradictory instructions
  • Provide clear, specific goals
```

### PARTIAL_SUCCESS

**Description**: Some work completed, but hit a blocker

**Common Causes:**
- Test failures after implementation
- Discovered missing dependencies mid-task
- Edge case not covered in prompt
- Unexpected file structure

**Retry Decision:**
- ✅ Often retryable with adjusted approach
- ✅ May need to complete remaining work manually

**Recovery Actions:**
```python
# Suggested by system:
- "Complete remaining work: <specific steps>"
- "Fix blocker: <specific issue>"
- "Adjust approach: <alternative strategy>"
```

**Example:**
```
Child agent failed: Implemented feature but tests fail with import error

Category: partial
Duration: 145.2s
Retryable: Yes

Work completed before failure:
  ✓ Implemented authentication logic
  ✓ Created test file

Files modified: src/auth.py, tests/test_auth.py

Blocked on: ImportError in tests: cannot import 'bcrypt'

Suggested recovery actions:
  • Install bcrypt: pip install bcrypt
  • Add bcrypt to requirements.txt
  • Retry tests after installation
```

## Failure Report Structure

### Standard Format

```
Child agent failed: <human-readable error message>

Category: <failure_category>
Duration: <execution_time>s
Retryable: <Yes|No>

Work completed before failure:
  ✓ <completed step 1>
  ✓ <completed step 2>
  ...

Files modified: <comma-separated list or 'none'>

Blocked on: <specific blocker description>

Suggested recovery actions:
  • <actionable step 1>
  • <actionable step 2>
  • <actionable step 3>

<task_metadata>
  <session_id>child-xyz</session_id>
  <status>failed</status>
  <failure_category>timeout|tool_error|missing_context|invalid_task|partial</failure_category>
  <retryable>true|false</retryable>
</task_metadata>
```

### ChildFailure Dataclass

```python
@dataclass
class ChildFailure:
    category: FailureCategory
    message: str
    session_id: str
    duration: float

    # Partial progress
    completed_steps: list[str]
    files_modified: list[str]

    # Recovery guidance
    blocked_on: Optional[str]
    suggested_retry: bool
    suggested_actions: list[str]

    # Execution context
    tool_usage: dict[str, int]
    last_successful_tool: Optional[str]
```

## Recovery Strategies

### Timeout Recovery

```python
def handle_timeout(result: str) -> str:
    """Handle timeout failures with intelligent retry."""

    if "<failure_category>timeout</failure_category>" not in result:
        return result

    # Check if retry is suggested
    if "<retryable>true</retryable>" in result:
        # Extract original timeout from context
        original_timeout = 300

        # Double timeout and retry
        return delegate_task(
            prompt=original_prompt,
            timeout=original_timeout * 2
        )
    else:
        # No progress - break into subtasks
        subtasks = decompose_task(original_prompt)
        results = []

        for subtask in subtasks:
            result = delegate_task(prompt=subtask, timeout=300)
            results.append(result)

        return aggregate_results(results)
```

### Tool Error Recovery

```python
def handle_tool_error(result: str) -> str:
    """Handle tool errors by fixing environment."""

    if "<failure_category>tool_error</failure_category>" not in result:
        return result

    # Extract error message
    error_match = re.search(r"Blocked on: (.+)", result)
    if error_match:
        error_msg = error_match.group(1)

        # Auto-fix common issues
        if "ModuleNotFoundError" in error_msg:
            module = extract_module_name(error_msg)
            run(f"pip install {module}")
            return delegate_task(prompt=original_prompt, timeout=300)

        elif "permission denied" in error_msg.lower():
            file_path = extract_file_path(error_msg)
            run(f"chmod +x {file_path}")
            return delegate_task(prompt=original_prompt, timeout=300)

    # Manual intervention needed
    return result
```

### Missing Context Recovery

```python
def handle_missing_context(result: str, context: dict) -> str:
    """Handle missing context by enriching prompt."""

    if "<failure_category>missing_context</failure_category>" not in result:
        return result

    # Enrich prompt with additional context
    enriched_prompt = f"""
{original_prompt}

Additional Context:
- Project root: {context['project_root']}
- Main files: {', '.join(context['main_files'])}
- Configuration: {context['config_path']}
- Test directory: {context['test_dir']}
"""

    return delegate_task(prompt=enriched_prompt, timeout=300)
```

### Partial Success Recovery

```python
def handle_partial_success(result: str) -> str:
    """Handle partial success by completing remaining work."""

    if "<failure_category>partial</failure_category>" not in result:
        return result

    # Extract completed steps and blocker
    completed = extract_completed_steps(result)
    blocker = extract_blocker(result)

    # Create focused prompt for remaining work
    continuation_prompt = f"""
Continue from previous attempt:

Already completed:
{chr(10).join(f'✓ {step}' for step in completed)}

Blocker encountered: {blocker}

Please:
1. Address the blocker
2. Complete the remaining work
3. Verify everything works
"""

    return delegate_task(prompt=continuation_prompt, timeout=300)
```

## Best Practices

### Design Prompts for Recoverability

**✅ Good:**
```python
delegate_task(
    prompt="""
    Implement user authentication:
    1. Add bcrypt to requirements.txt
    2. Implement password hashing in src/auth.py
    3. Add tests in tests/test_auth.py
    4. Run tests to verify

    Files to modify:
    - src/auth.py (add hash_password, verify_password functions)
    - tests/test_auth.py (add test cases)
    - requirements.txt (add bcrypt)
    """,
    timeout=300
)
```

**❌ Bad:**
```python
delegate_task(
    prompt="Add auth using the approach we discussed",
    timeout=300
)
```

### Handle Failures Gracefully

**✅ Good:**
```python
result = delegate_task(prompt="Complex task", timeout=300)

if "<status>failed</status>" in result:
    category = extract_category(result)

    if category == "timeout" and is_retryable(result):
        # Intelligent retry
        result = delegate_task(prompt="Complex task", timeout=600)

    elif category == "tool_error":
        # Fix environment
        fix_environment(result)
        result = delegate_task(prompt="Complex task", timeout=300)

    elif category == "partial":
        # Complete remaining work
        result = complete_remaining_work(result)
```

**❌ Bad:**
```python
result = delegate_task(prompt="Complex task", timeout=300)
# Assume success, don't check for failures
```

### Log Failures for Analysis

```python
def delegate_with_logging(prompt: str, timeout: float) -> str:
    result = delegate_task(prompt=prompt, timeout=timeout)

    if "<status>failed</status>" in result:
        # Log failure for later analysis
        log_failure({
            "prompt": prompt,
            "timeout": timeout,
            "category": extract_category(result),
            "blocker": extract_blocker(result),
            "files_modified": extract_files_modified(result),
            "timestamp": datetime.now().isoformat()
        })

    return result
```

## Parsing Failure Reports

### Extract Failure Category

```python
def extract_category(result: str) -> Optional[str]:
    """Extract failure category from result."""
    match = re.search(r"<failure_category>(.+?)</failure_category>", result)
    return match.group(1) if match else None
```

### Extract Retryable Status

```python
def is_retryable(result: str) -> bool:
    """Check if failure is retryable."""
    return "<retryable>true</retryable>" in result
```

### Extract Completed Work

```python
def extract_completed_steps(result: str) -> list[str]:
    """Extract completed steps from failure report."""
    steps = []
    in_completed_section = False

    for line in result.split('\n'):
        if "Work completed before failure:" in line:
            in_completed_section = True
            continue
        if in_completed_section:
            if line.strip().startswith('✓'):
                steps.append(line.strip()[2:])  # Remove ✓
            elif line.strip().startswith('Files modified:'):
                break

    return steps
```

### Extract Files Modified

```python
def extract_files_modified(result: str) -> list[str]:
    """Extract modified files from failure report."""
    match = re.search(r"Files modified: (.+)", result)
    if match:
        files_str = match.group(1)
        if files_str == 'none':
            return []
        return [f.strip() for f in files_str.split(',')]
    return []
```

### Extract Blocker

```python
def extract_blocker(result: str) -> Optional[str]:
    """Extract blocker description from failure report."""
    match = re.search(r"Blocked on: (.+)", result)
    return match.group(1) if match else None
```

### Extract Suggested Actions

```python
def extract_suggested_actions(result: str) -> list[str]:
    """Extract suggested recovery actions."""
    actions = []
    in_actions_section = False

    for line in result.split('\n'):
        if "Suggested recovery actions:" in line:
            in_actions_section = True
            continue
        if in_actions_section:
            if line.strip().startswith('•'):
                actions.append(line.strip()[2:])  # Remove •
            elif line.strip().startswith('<task_metadata>'):
                break

    return actions
```

## Automated Recovery Workflows

### Retry Loop with Exponential Backoff

```python
async def delegate_with_retry(
    prompt: str,
    max_retries: int = 3,
    base_timeout: float = 300.0
) -> str:
    """Delegate with automatic retry on recoverable failures."""

    for attempt in range(max_retries):
        timeout = base_timeout * (2 ** attempt)  # Exponential backoff

        result = delegate_task(prompt=prompt, timeout=timeout)

        if "<status>completed</status>" in result:
            return result

        if "<status>failed</status>" in result:
            category = extract_category(result)
            retryable = is_retryable(result)

            if not retryable:
                # Non-retryable failure
                return result

            if category == "timeout":
                # Continue with increased timeout
                continue

            elif category == "tool_error":
                # Try to fix environment
                if attempt < max_retries - 1:
                    await fix_environment_from_error(result)
                    continue

            elif category == "partial":
                # Complete remaining work
                blocker = extract_blocker(result)
                await address_blocker(blocker)
                continue

    return result  # Max retries exceeded
```

### Smart Task Decomposition

```python
def delegate_with_decomposition(prompt: str, timeout: float) -> str:
    """Delegate with automatic task decomposition on timeout."""

    result = delegate_task(prompt=prompt, timeout=timeout)

    if "<failure_category>timeout</failure_category>" in result:
        if not is_retryable(result):
            # No progress - decompose
            subtasks = decompose_task(prompt)
            results = []

            for i, subtask in enumerate(subtasks):
                print(f"Executing subtask {i+1}/{len(subtasks)}")
                subtask_result = delegate_task(
                    prompt=subtask,
                    timeout=timeout // len(subtasks)
                )
                results.append(subtask_result)

            return aggregate_results(results)

    return result
```

## Testing Failure Scenarios

### Unit Tests

```python
def test_timeout_failure_analysis():
    """Test timeout failure categorization."""
    failure = _analyze_timeout_failure(
        child_agent=mock_agent_with_progress,
        session_id="test-123",
        duration=300.0,
        timeout=300.0,
        prompt="Test task"
    )

    assert failure.category == FailureCategory.TIMEOUT
    assert failure.suggested_retry is True
    assert "Retry with timeout=600s" in failure.suggested_actions

def test_tool_error_analysis():
    """Test tool error categorization."""
    exception = PermissionError("Permission denied: /etc/config")

    failure = _analyze_exception_failure(
        exception=exception,
        child_agent=mock_agent,
        session_id="test-456",
        duration=23.5,
        prompt="Test task"
    )

    assert failure.category == FailureCategory.TOOL_ERROR
    assert failure.suggested_retry is True
    assert "Check file permissions" in failure.suggested_actions
```

### Integration Tests

```python
async def test_delegation_timeout_recovery():
    """Test timeout handling in delegation flow."""

    # Simulate timeout
    with pytest.raises(asyncio.TimeoutError):
        await delegate_task_impl(
            prompt="Long task",
            timeout=0.1,  # Very short timeout
            ...
        )

    # Should return structured failure report
    # (actual test would capture the return value)
```

## Monitoring and Alerts

### Track Failure Rates

```python
def monitor_delegation_failures():
    """Monitor and report on delegation failures."""

    # Query session events
    failures = query_session_events(
        event_type="delegation_error",
        time_range="last_24h"
    )

    # Categorize failures
    by_category = defaultdict(int)
    for failure in failures:
        category = failure['metadata']['category']
        by_category[category] += 1

    # Alert if high failure rate
    total = len(failures)
    if total > THRESHOLD:
        alert(f"High delegation failure rate: {total} failures in 24h")

    # Report by category
    for category, count in by_category.items():
        print(f"{category}: {count} ({count/total*100:.1f}%)")
```

### Common Failure Patterns

```python
def analyze_failure_patterns():
    """Identify common failure patterns for optimization."""

    failures = load_recent_failures()

    # Group by blocker
    by_blocker = defaultdict(list)
    for f in failures:
        blocker = extract_blocker(f['result'])
        by_blocker[blocker].append(f)

    # Identify top blockers
    top_blockers = sorted(
        by_blocker.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )[:10]

    # Report
    for blocker, occurrences in top_blockers:
        print(f"{blocker}: {len(occurrences)} occurrences")
```

## Future Enhancements

### Machine Learning Integration

- Predict failure likelihood before delegation
- Suggest optimal timeout based on task complexity
- Auto-generate recovery strategies from historical data
- Identify task patterns prone to specific failures

### Advanced Recovery

- Automatic environment repair
- Smart task decomposition based on failure analysis
- Cross-session learning from similar failures
- Proactive context enrichment

### User Experience

- Interactive recovery prompts
- Failure visualization dashboard
- Recovery action templates
- Success rate predictions
