"""
这个文件负责定义和创建全局事件和标志，这些事件可以在整个 Faust 应用中被不同的模块共享和使用。
"""
import asyncio
backend2frontendQueue_event = asyncio.Event()
HIL_feedback_event = asyncio.Event()
HIL_feedback_fail_event= asyncio.Event()

ignore_trigger_event = asyncio.Event()

feedback_event_pool={}
def create_feedback_event(feedback_id):
    """Creates a new asyncio.Event for a specific feedback ID and stores it in the feedback_event_pool."""
    event = asyncio.Event()
    feedback_event_pool[feedback_id] = event
    return event