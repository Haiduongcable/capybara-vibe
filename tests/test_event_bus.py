"""Tests for event bus."""

import asyncio
import pytest

from capybara.core.event_bus import EventBus, Event, EventType


@pytest.mark.asyncio
async def test_publish_subscribe():
    """Test basic publish/subscribe functionality."""
    bus = EventBus()
    session_id = "test123"

    events_received = []

    async def subscriber():
        async for event in bus.subscribe(session_id):
            events_received.append(event)

    # Start subscriber
    subscriber_task = asyncio.create_task(subscriber())

    # Give subscriber time to register
    await asyncio.sleep(0.1)

    # Publish events
    await bus.publish(Event(session_id, EventType.TOOL_START, "bash"))
    await bus.publish(Event(session_id, EventType.TOOL_DONE, "bash"))
    await bus.publish(Event(session_id, EventType.AGENT_DONE))

    # Wait for subscriber to finish (stops after AGENT_DONE)
    await subscriber_task

    assert len(events_received) == 3
    assert events_received[0].event_type == EventType.TOOL_START
    assert events_received[0].tool_name == "bash"
    assert events_received[1].event_type == EventType.TOOL_DONE
    assert events_received[2].event_type == EventType.AGENT_DONE


@pytest.mark.asyncio
async def test_late_subscriber_gets_history():
    """Test that late subscribers receive event history."""
    bus = EventBus()
    session_id = "test123"

    # Publish before subscription
    await bus.publish(Event(session_id, EventType.TOOL_START, "bash"))
    await bus.publish(Event(session_id, EventType.TOOL_DONE, "bash"))

    events_received = []

    async def subscriber():
        async for event in bus.subscribe(session_id):
            events_received.append(event)
            if event.event_type == EventType.TOOL_DONE:
                break

    await subscriber()

    # Should receive history
    assert len(events_received) == 2
    assert events_received[0].event_type == EventType.TOOL_START
    assert events_received[1].event_type == EventType.TOOL_DONE


@pytest.mark.asyncio
async def test_multiple_subscribers():
    """Test multiple subscribers to same session."""
    bus = EventBus()
    session_id = "test123"

    events_1 = []
    events_2 = []

    async def subscriber_1():
        async for event in bus.subscribe(session_id):
            events_1.append(event)

    async def subscriber_2():
        async for event in bus.subscribe(session_id):
            events_2.append(event)

    # Start both subscribers
    task1 = asyncio.create_task(subscriber_1())
    task2 = asyncio.create_task(subscriber_2())

    await asyncio.sleep(0.1)

    # Publish events
    await bus.publish(Event(session_id, EventType.TOOL_START, "read_file"))
    await bus.publish(Event(session_id, EventType.TOOL_DONE, "read_file"))
    await bus.publish(Event(session_id, EventType.AGENT_DONE))

    await asyncio.gather(task1, task2)

    # Both should receive all events
    assert len(events_1) == 3
    assert len(events_2) == 3


@pytest.mark.asyncio
async def test_different_sessions_isolated():
    """Test events from different sessions are isolated."""
    bus = EventBus()
    session_1 = "session1"
    session_2 = "session2"

    events_1 = []
    events_2 = []

    async def subscriber_1():
        async for event in bus.subscribe(session_1):
            events_1.append(event)

    async def subscriber_2():
        async for event in bus.subscribe(session_2):
            events_2.append(event)

    task1 = asyncio.create_task(subscriber_1())
    task2 = asyncio.create_task(subscriber_2())

    await asyncio.sleep(0.1)

    # Publish to session 1
    await bus.publish(Event(session_1, EventType.TOOL_START, "bash"))
    await bus.publish(Event(session_1, EventType.AGENT_DONE))

    # Publish to session 2
    await bus.publish(Event(session_2, EventType.TOOL_START, "grep"))
    await bus.publish(Event(session_2, EventType.AGENT_DONE))

    await asyncio.gather(task1, task2)

    # Each should only see their session's events
    assert len(events_1) == 2
    assert all(e.session_id == session_1 for e in events_1)

    assert len(events_2) == 2
    assert all(e.session_id == session_2 for e in events_2)


@pytest.mark.asyncio
async def test_history_trimming():
    """Test that history is trimmed to max_history."""
    bus = EventBus()
    session_id = "test123"

    # Publish more than max_history events
    for i in range(150):
        await bus.publish(Event(session_id, EventType.TOOL_START, f"tool_{i}"))

    # Get with high limit to see actual stored history
    history = bus.get_recent(session_id, limit=200)

    # Should only keep last 100
    assert len(history) == 100
    assert history[0].tool_name == "tool_50"  # First kept event
    assert history[-1].tool_name == "tool_149"  # Last event


@pytest.mark.asyncio
async def test_cleanup_session():
    """Test session cleanup removes data."""
    bus = EventBus()
    session_id = "test123"

    # Publish events
    await bus.publish(Event(session_id, EventType.TOOL_START, "bash"))

    # Verify history exists
    assert len(bus.get_recent(session_id)) == 1

    # Cleanup
    bus.cleanup_session(session_id)

    # History should be empty
    assert len(bus.get_recent(session_id)) == 0


@pytest.mark.asyncio
async def test_get_recent_with_limit():
    """Test get_recent with custom limit."""
    bus = EventBus()
    session_id = "test123"

    # Publish 10 events
    for i in range(10):
        await bus.publish(Event(session_id, EventType.TOOL_START, f"tool_{i}"))

    # Get last 5
    recent = bus.get_recent(session_id, limit=5)

    assert len(recent) == 5
    assert recent[0].tool_name == "tool_5"
    assert recent[-1].tool_name == "tool_9"
