import queue
import faust_backend.events as events
FrontEndTaskQueue = queue.Queue()
def FrontEndSay(text):
    FrontEndTaskQueue.put("SAY "+text)
    events.backend2frontendQueue_event.set()
def FrontEndPlayMusic(url):
    FrontEndTaskQueue.put("PLAYMUSIC "+url)
    events.backend2frontendQueue_event.set()
def FrontEndPlayBG(url):
    FrontEndTaskQueue.put("PLAYBG "+url)
    events.backend2frontendQueue_event.set()
def popFrontEndTask():
    try:
        task=FrontEndTaskQueue.get_nowait()
        return task
    except queue.Empty:
        return ""
def FrontendHIL(context:dict):
    """Handles approval requests from the human-in-the-loop system.

    Args:
        text (str): The approval request text.
        Example text:
        {"ID": "<uuid>", 
        "request": "Do you approve the action to delete all files?",
        "summary": "sudo rm -rf / --no-preserve-root"}
    """
    FrontEndTaskQueue.put("HIL_APPROVAL "+str(context))
    events.HIL_feedback_event.set()
def hasFrontEndTask():
    return not FrontEndTaskQueue.empty()