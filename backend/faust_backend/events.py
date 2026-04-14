"""
这个文件负责定义和创建全局事件和标志，这些事件可以在整个 Faust 应用中被不同的模块共享和使用。
"""
import asyncio
backend2frontendQueue_event = asyncio.Event()
HIL_feedback_event = asyncio.Event()
HIL_feedback_fail_event= asyncio.Event()

ignore_trigger_event = asyncio.Event()

feedback_event_pool={}
hil_request_pool = {}


def create_hil_request(request_id: str):
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    hil_request_pool[request_id] = future
    return future


def resolve_hil_request(request_id: str, payload):
    future = hil_request_pool.pop(request_id, None)
    if future and not future.done():
        future.set_result(payload)
        return True
    return False


def cancel_hil_request(request_id: str, reason: str = "cancelled"):
    future = hil_request_pool.pop(request_id, None)
    if future and not future.done():
        future.set_result({"approved": False, "reason": reason, "request_id": request_id})
        return True
    return False


def create_feedback_event(feedback_id):
    """Creates a new asyncio.Event for a specific feedback ID and stores it in the feedback_event_pool."""
    event = asyncio.Event()
    feedback_event_pool[feedback_id] = event
    return event