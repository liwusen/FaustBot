import queue
import json
import asyncio
try:
    import faust_backend.events as events
except ImportError:
    import events
import uuid
FrontEndTaskQueue = queue.Queue()


def _push_command(command: str, payload=None):
    if payload is None:
        FrontEndTaskQueue.put(command)
    else:
        FrontEndTaskQueue.put(command + " " + json.dumps(payload, ensure_ascii=False))
    events.backend2frontendQueue_event.set()


def FrontEndSay(text):
    _push_command("SAY", text)


def FrontEndPlayMusic(url):
    _push_command("PLAYMUSIC", url)


def FrontEndPlayBG(url):
    _push_command("PLAYBG", url)


def FrontEndShowNimbleWindow(payload: dict):
    """Send a nimble window payload to the frontend.

    payload example:
    {
      "callback_id": "nimble_xxx",
      "title": "安装确认",
      "html": "<div>...</div>",
      "lifespan": 600,
      "expires_at": 1234567890.0,
      "metadata": {...}
    }
    """
    _push_command("NIMBLE_SHOW", payload)


def FrontEndCloseNimbleWindow(payload: dict)->None:
    _push_command("NIMBLE_CLOSE", payload)


def popFrontEndTask()->str:
    try:
        task=FrontEndTaskQueue.get_nowait()
        return task
    except queue.Empty:
        return ""
def FrontendHIL(context:dict)->None:
    """Handles approval requests from the human-in-the-loop system.

    Args:
        text (str): The approval request text.
        Example text:
        {"ID": "<uuid>", 
        "request": "Do you approve the action to delete all files?",
        "summary": "sudo rm -rf / --no-preserve-root"}
    """
    _push_command("HIL_APPROVAL", context)
def hasFrontEndTask():
    return not FrontEndTaskQueue.empty()

async def frontendGetMotions()->str:
    """Fetches the motions of the model from the frontend.

    Returns:
        fid: A unique feedback ID that can be used to wait for the motion data to be returned from the frontend.
    """
    _push_command("GET_MOTIONS")
    events.create_feedback_event(fid:="motions-fetch-"+uuid.uuid4().hex)
    return fid
def frontendSetMotion(motion:dict)->None:
    """Sends motion data to the frontend.

    Args:
        motion (dict): A dictionary containing the motion data to be sent to the frontend.
    """
    _push_command("SET_MOTION", motion)
async def demo():
    print(fid:=await frontendGetMotions())
    print(events.feedback_event_pool)
if __name__ == "__main__":
    # Example usage
    print(asyncio.run(demo()))