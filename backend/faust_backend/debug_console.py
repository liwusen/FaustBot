import threading
import time
import json

import requests

try:
    import websocket  # websocket-client
except Exception:
    raise SystemExit("缺少依赖 websocket-client。请运行: pip install websocket-client")

HTTP_URL = "http://127.0.0.1:13900/faust/chat"
WS_URL = "ws://127.0.0.1:13900/faust/command"
CHAT_WS_URL = "ws://127.0.0.1:13900/faust/chat"

def start_ws_listener():
    def on_message(ws, message):
        try:
            print("\n[WS MESSAGE]", message)
        except Exception:
            print("\n[WS MESSAGE] (无法解析)", message)

    def on_error(ws, error):
        print("\n[WS ERROR]", error)

    def on_close(ws, close_status_code, close_msg):
        print("\n[WS CLOSED]", close_status_code, close_msg)

    def on_open(ws):
        print("[WS OPENED] Listening for server pushes...")

    ws_app = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
    )

    # run forever in daemon thread so main thread can do HTTP calls
    th = threading.Thread(target=ws_app.run_forever, kwargs={"ping_interval": 20}, daemon=True)
    th.start()
    return ws_app, th


def chat_request(text):
    try:
        state = {
            "reply": "",
            "error": None,
        }

        def on_message(ws, message):
            try:
                json_msg = json.loads(message)
                msg_type = json_msg.get("type")
                if msg_type == "delta":
                    chunk = json_msg.get("content", "")
                    state["reply"] += chunk
                    print(chunk, end="", flush=True)
                elif msg_type == "done":
                    final_reply = json_msg.get("reply", state["reply"])
                    state["reply"] = final_reply
                    print("\n[CHAT DONE]", final_reply)
                    ws.close()
                elif msg_type == "error":
                    error_msg = json_msg.get("error") or json_msg.get("message") or message
                    state["error"] = error_msg
                    print("\n[CHAT ERROR]", error_msg)
                    ws.close()
                else:
                    print("\n[WS MESSAGE]", json_msg)
            except Exception:
                print("\n[WS MESSAGE] (无法解析)", message)

        def on_error(ws, error):
            state["error"] = str(error)
            print("\n[CHAT WS ERROR]", error)

        def on_close(ws, close_status_code, close_msg):
            if close_status_code or close_msg:
                print("\n[CHAT WS CLOSED]", close_status_code, close_msg)

        def on_open(ws):
            payload = json.dumps({"text": text}, ensure_ascii=False)
            ws.send(payload)

        ws_chat_app = websocket.WebSocketApp(
            CHAT_WS_URL,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )
        print("[INFO] 已发送聊天请求，等待响应...")
        ws_chat_app.run_forever()
        if state["error"]:
            return {"error": state["error"]}
        return {"reply": state["reply"]}
    except Exception as e:
        return {"error": f"请求失败: {e}"}

def main():
    print("debug-console 启动。HTTP:", HTTP_URL, "WS:", WS_URL)
    print("说明: 输入文本并回车发送到 /faust/chat。输入 exit 或 Ctrl+C 退出。")
    if input("WS 监听器启动？(Y/n)> ").strip().lower() not in ("n", "no"):
        start_ws_listener()
        print("WS 监听器已启动。")
    else:
        print("WS 监听器未启动。")
    try:
        while True:
            try:
                text = input("\n输入> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n退出中...")
                break
            if not text:
                continue
            elif text.lower() in ("exit", "quit"):
                print("退出中...")
                break
            elif text.lower().startswith("ws"):
                requests.post(HTTP_URL.replace("/faust/chat", "/faust/command/forward"), json={"command": text[2:].strip()})
                print("[INFO] 已通过 /faust/command/forward 转发命令到 WS。")
                print("[WS COMMAND]", text[2:].strip(),sep="")
                continue
            elif text.lower().startswith("hil-accept"):
                requests.post(HTTP_URL.replace("/faust/chat", "/faust/humanInLoop/feedback"), json={"feedback": True})
                print("[HIL FEEDBACK]accept", text[3:].strip(),sep="")
                continue
            elif text.lower().startswith("hil-reject"):
                requests.post(HTTP_URL.replace("/faust/chat", "/faust/humanInLoop/feedback"), json={"feedback": False})
                print("[HIL FEEDBACK]", text[3:].strip(),sep="")
                continue
            result = chat_request(text)
            if isinstance(result, dict) and result.get("error"):
                print("[CHAT REQUEST ERROR]", result["error"])

    except KeyboardInterrupt:
        pass
    # give ws thread a moment to print final messages
    time.sleep(0.3)
    print("已退出。")


if __name__ == "__main__":
    while True:
        main()
        time.sleep(1)
        print("重新启动 debug-console...")