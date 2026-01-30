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


def chat_request(text: str, timeout: int = 30):
    try:
        r = requests.post(HTTP_URL, json={"text": text}, timeout=timeout)
    except Exception as e:
        return {"error": f"请求失败: {e}"}
    try:
        return r.json()
    except Exception:
        return {"raw": r.text}


def main():
    print("debug-console 启动。HTTP:", HTTP_URL, "WS:", WS_URL)
    print("说明: 输入文本并回车发送到 /faust/chat。输入 exit 或 Ctrl+C 退出。")
    start_ws_listener()

    try:
        while True:
            try:
                text = input("\n输入> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n退出中...")
                break
            if not text:
                continue
            if text.lower() in ("exit", "quit"):
                print("退出中...")
                break
            resp = chat_request(text)
            if "reply" in resp:
                print("[REPLY]", resp["reply"])
            elif "error" in resp:
                print("[ERROR]", resp["error"])
            else:
                # fallback: pretty print whatever returned
                print("[HTTP RESPONSE]", json.dumps(resp, ensure_ascii=False, indent=2))
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