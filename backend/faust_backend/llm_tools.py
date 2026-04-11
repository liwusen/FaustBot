from langchain.tools import tool
import os

import faust_backend.config_loader as conf
os.environ["SEARCHAPI_API_KEY"]=conf.SEARCH_API_KEY
import faust_backend.backend2front as backend2frontend
from faust_backend.utils import *

import functools,inspect,os,sys
import socket
import io
import datetime
import re
import tempfile
import zipfile
import shutil
import requests
import faust_backend.gui_llm_lib as gui_llm_lib
import faust_backend.trigger_manager as trigger_manager
import faust_backend.nimble as nimble
import faust_backend.rag_client as rag_client
import faust_backend.minecraft_client as minecraft_client
import winsound
import asyncio
import faust_backend.events as events
import json
import threading
import time
import uuid
from pathlib import Path
import faust_backend.utils as utils
toollist=[]
DIARY_DIR=Path("agents") / Path(conf.AGENT_NAME) / "diary" 
STARTED=False
ORIGINAL_TOOL_FUNCS={}
RAG_ASYNC_RESULTS: dict[str, dict] = {}
RAG_ASYNC_LOCK = threading.Lock()
RAG_TRACKER = rag_client.create_tracker()


def refresh_runtime_paths() -> None:
    global DIARY_DIR, RAG_TRACKER
    DIARY_DIR = Path("agents") / Path(conf.AGENT_NAME) / "diary"
    if hasattr(RAG_TRACKER, "refresh_runtime"):
        RAG_TRACKER.refresh_runtime(conf.AGENT_ROOT, getattr(conf, "RAG_API_URL", None))
    else:
        RAG_TRACKER = rag_client.create_tracker(conf.AGENT_ROOT, getattr(conf, "RAG_API_URL", None))


def _safe_read_file_range(file_path: str, start_line: int, end_line: int) -> str:
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return f"文件不存在: {file_path}"
    if start_line < 1:
        start_line = 1
    with p.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    if total == 0:
        return f"File: `{file_path}`. Empty file."
    if end_line <= 0 or end_line > total:
        end_line = total
    if start_line > end_line:
        return f"无效行范围: start_line={start_line}, end_line={end_line}"
    body = "".join(lines[start_line - 1:end_line])
    return f"File: `{file_path}`. Lines {start_line} to {end_line} ({total} lines total):\n{body}"


def _extract_section_chunks(patch_text: str) -> list[tuple[str, str, list[str]]]:
    lines = patch_text.splitlines()
    if not lines:
        raise ValueError("Patch 为空")
    if lines[0].strip() != "*** Begin Patch" or lines[-1].strip() != "*** End Patch":
        raise ValueError("Patch 必须以 *** Begin Patch 开始并以 *** End Patch 结束")

    body = lines[1:-1]
    chunks: list[tuple[str, str, list[str]]] = []
    current_action = None
    current_path = None
    current_lines: list[str] = []

    header_re = re.compile(r"^\*\*\*\s+(Add|Update|Delete)\s+File:\s+(.+?)\s*$")
    for line in body:
        m = header_re.match(line)
        if m:
            if current_action and current_path is not None:
                chunks.append((current_action, current_path, current_lines))
            current_action = m.group(1)
            current_path = m.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_action and current_path is not None:
        chunks.append((current_action, current_path, current_lines))

    if not chunks:
        raise ValueError("Patch 中未找到任何文件操作段")
    return chunks


def _apply_update_hunks(original: str, section_lines: list[str]) -> str:
    i = 0
    content = original
    while i < len(section_lines):
        line = section_lines[i]
        if line.startswith("@@"):
            i += 1
            old_lines: list[str] = []
            new_lines: list[str] = []
            while i < len(section_lines) and not section_lines[i].startswith("@@"):
                row = section_lines[i]
                if row.startswith("-"):
                    old_lines.append(row[1:])
                elif row.startswith("+"):
                    new_lines.append(row[1:])
                i += 1

            old_chunk = "\n".join(old_lines)
            new_chunk = "\n".join(new_lines)
            if old_chunk:
                if old_chunk not in content:
                    raise ValueError(f"更新失败，未在文件中找到旧代码块:\n{old_chunk[:200]}")
                content = content.replace(old_chunk, new_chunk, 1)
            elif new_chunk:
                # 无旧块时，退化为追加
                if content and not content.endswith("\n"):
                    content += "\n"
                content += new_chunk
        else:
            i += 1
    return content


def _apply_patch_text(patch_text: str) -> str:
    chunks = _extract_section_chunks(patch_text)
    changed: list[str] = []
    for action, target_path, section_lines in chunks:
        p = Path(target_path)
        if action == "Add":
            p.parent.mkdir(parents=True, exist_ok=True)
            add_lines = [row[1:] if row.startswith("+") else row for row in section_lines]
            text = "\n".join(add_lines)
            if text and not text.endswith("\n"):
                text += "\n"
            p.write_text(text, encoding="utf-8")
            changed.append(f"Add {target_path}")
        elif action == "Delete":
            if p.exists():
                p.unlink()
            changed.append(f"Delete {target_path}")
        elif action == "Update":
            if not p.exists() or not p.is_file():
                raise ValueError(f"Update 失败，文件不存在: {target_path}")
            old = p.read_text(encoding="utf-8")
            new = _apply_update_hunks(old, section_lines)
            p.write_text(new, encoding="utf-8")
            changed.append(f"Update {target_path}")
        else:
            raise ValueError(f"不支持的 patch 动作: {action}")

    return "Patch 应用成功:\n" + "\n".join(changed)


def _find_skill_root(extract_dir: Path) -> Path:
    candidates = [p.parent for p in extract_dir.rglob("_meta.json") if p.is_file()]
    if not candidates:
        raise ValueError("skill 包中未找到 _meta.json")
    if len(candidates) == 1:
        return candidates[0]
    for c in candidates:
        if (c / "SKILL.md").exists():
            return c
    return candidates[0]


def _install_skill_from_slug(slug: str, overwrite: bool = False) -> dict:
    api = f"https://wry-manatee-359.convex.site/api/v1/download?slug={requests.utils.quote(slug, safe='')}"
    with tempfile.TemporaryDirectory(prefix="faust-skill-") as td:
        td_path = Path(td)
        zip_path = td_path / "skill.zip"
        extract_dir = td_path / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        resp = requests.get(api, timeout=60)
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as exc:
            raise ValueError("下载结果不是有效 ZIP") from exc

        skill_root = _find_skill_root(extract_dir)
        meta_file = skill_root / "_meta.json"
        skill_doc = skill_root / "SKILL.md"
        if not skill_doc.exists():
            raise ValueError("skill 包缺少 SKILL.md")

        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        skill_slug = str(meta.get("slug") or slug).strip()
        version = str(meta.get("version") or "0.0.0").strip()
        if not skill_slug:
            raise ValueError("skill slug 为空")

        agent_name = str(conf.AGENT_NAME)
        skill_dir = Path("agents") / agent_name / "skill.d"
        skill_dir.mkdir(parents=True, exist_ok=True)
        target_dir = skill_dir / skill_slug

        if target_dir.exists() and not overwrite:
            raise ValueError(f"skill 已存在: {skill_slug}，如需覆盖请设置 overwrite=true")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(skill_root, target_dir)

        index_file = skill_dir / "skills.state.json"
        state = {"skills": {}}
        if index_file.exists():
            try:
                state = json.loads(index_file.read_text(encoding="utf-8"))
                if not isinstance(state, dict):
                    state = {"skills": {}}
            except Exception:
                state = {"skills": {}}

        skills = state.setdefault("skills", {})
        skills[skill_slug] = {
            "slug": skill_slug,
            "version": version,
            "installed_at": datetime.datetime.now().isoformat(),
            "enabled": True,
            "source": api,
            "path": str(target_dir.resolve()),
        }
        index_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "slug": skill_slug,
            "version": version,
            "agent": agent_name,
            "path": str(target_dir.resolve()),
            "source": api,
        }
#define add to TOOLLIST wrapper
def __init__():
    print("[llm_tools] Initializing llm_tools module...")
def add_to_tool_list(func):
    toollist.append(func)
    return func
def record_func_name(func):
    func_name=func.__name__
    ORIGINAL_TOOL_FUNCS[func_name]=func
    print(f"[llm_tools] Registered tool: {func_name}")
    return func


def _store_rag_async_result(callback_id: str, data: dict) -> None:
    with RAG_ASYNC_LOCK:
        RAG_ASYNC_RESULTS[callback_id] = data


def _get_rag_async_result(callback_id: str) -> dict | None:
    with RAG_ASYNC_LOCK:
        return RAG_ASYNC_RESULTS.get(callback_id)


def _run_async_in_thread(coro) -> None:
    def runner():
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)
        finally:
            try:
                loop.close()
            except Exception:
                pass

    threading.Thread(target=runner, daemon=True).start()


async def _rag_query_async_job(callback_id: str, query: str, mode: str, only_need_context: bool) -> None:
    started_at = time.time()
    try:
        result = await rag_client.rag_query(
            query,
            mode=mode,
            only_need_context=only_need_context,
            enable_rerank=False,
        )
        payload = {
            "status": "done",
            "callback_id": callback_id,
            "query": query,
            "mode": mode,
            "only_need_context": only_need_context,
            "result": result,
            "started_at": started_at,
            "finished_at": time.time(),
        }
    except Exception as e:
        payload = {
            "status": "error",
            "callback_id": callback_id,
            "query": query,
            "mode": mode,
            "only_need_context": only_need_context,
            "error": str(e),
            "started_at": started_at,
            "finished_at": time.time(),
        }

    _store_rag_async_result(callback_id, payload)
    trigger_manager.append_trigger({
        "id": f"rag_async_result_{callback_id}",
        "type": "datetime",
        "target": datetime.datetime.now().isoformat(),
        "recall_description": f"RAG 异步查询已完成。请使用 ragQueryAsyncGetTool 获取结果，callback_id={callback_id}",
        "lifespan": 600,
    })
async def HILRequest(id,title,summary):
    if not STARTED:
        return False,"cannot call HILRequest before the system is fully started."
    backend2frontend.FrontendHIL({"ID": id,"request": title,"summary": summary})
    events.HIL_feedback_event.clear()
    events.HIL_feedback_fail_event.clear()
    ok_callback=asyncio.create_task(events.HIL_feedback_event.wait())
    fail_callback=asyncio.create_task(events.HIL_feedback_fail_event.wait())
    timeout_callback=asyncio.create_task(asyncio.sleep(30)) # 30 seconds timeout
    done,_=await asyncio.wait([ok_callback,fail_callback,timeout_callback],return_when=asyncio.FIRST_COMPLETED)
    if ok_callback in done:
        events.HIL_feedback_event.clear()
        events.HIL_feedback_fail_event.clear()
        return True,"approved"
    elif fail_callback in done:
        events.HIL_feedback_fail_event.clear()
        events.HIL_feedback_event.clear()
        return False,"rejected"
    elif timeout_callback in done:
        return False,"timeout"
    else:
        return False,"unknown"
    
@add_to_tool_list#记录最终TOOL
@tool#把函数注册为工具，供LLM调用
@record_func_name#记录原始函数，方便后续调用和管理
def getDateTimeTool()->str:
    """
    Description:
        获取当前的日期和时间，格式为YYYY-MM-DD HH:MM:SS
    Args:
        None
    Returns:
        str: 当前的日期和时间字符串
    """
    from datetime import datetime
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")
@add_to_tool_list
@tool
@record_func_name
def userHostNameTool()->str:
    """
    Description:
        获取当前用户的电脑相关信息,包括用户名等
    Args:
        None
    Returns:
        str(json): 包含电脑相关信息的字典
    """

    hostname = socket.gethostname()
    with os.popen('whoami') as f:
        username = f.read().strip()
    ip=socket.gethostbyname(hostname)
    ip=ip.strip()
    os_type=os.name
    return str({"hostname": hostname,"username":username,"ip":ip,"os_type":os_type})
@add_to_tool_list
@tool
@record_func_name
def pythonExecTool(code: str) -> str:
    """
    Description:
        执行传入的Python代码，并返回执行结果或错误信息。
    Args:
        code (str): 需要执行的Python代码字符串。
    Returns:
        str: 执行结果的字符串表示（包括变量名和对应值,以及stdout），或者错误信息。
    """
    try:
        # 定义一个局部命名空间来执行代码
        # 捕获它的stdout
        # 以便在返回时包含输出结果
        local_namespace = {}
        sio = io.StringIO()
        print("[llm_tools.pythonExecTool] Executing code:", code)
        sys.stdout = sio
        try:
            exec(code, {}, local_namespace)
        finally:
            sys.stdout = sys.__stdout__
        # 获取所有局部变量的字符串表示
        result = "\n".join(f"{key} = {value}" for key, value in local_namespace.items())
        # 获取stdout的内容
        stdout_result = sio.getvalue()
        return result + "\n" + stdout_result if result or stdout_result else "代码执行成功，但没有返回值。"
    except Exception as e:
        return f"代码执行出错: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def sysExecTool(command: str,timeout:int=15) -> str:
    """
    Description:
        执行传入的系统命令，并返回命令的输出结果或错误信息。
        这个工具只应该在用户需要时执行。
    Args:
        command (str): 需要执行的系统命令字符串。
        timeout (int): 超时时间
    Returns:
        str: 命令的输出结果字符串，或者错误信息。
    """
    try:
        print("[llm_tools.sysExecTool] Executing command:", command)
        subp=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8')
        subp.wait(timeout)
        stdout,stderr=subp.communicate()
        stdout=stdout.decode(errors='ignore').strip()
        stderr=stderr.decode(errors='ignore').strip()
        return f"""执行完成。标准输出:\n{stdout}\n标准错误:\n{stderr}\n返回值{subp.returncode}"""
    except subprocess.TimeoutExpired as e:
        return f"命令超时"
    except Exception as e:
        return f"命令执行出错: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def listDiaryFilesTool() -> str:
    """
    Description:
        列出日记目录下的所有文件。
        你可以自行决定何时使用此工具。
    Args:
        None
    Returns:
        str: 日记目录下的文件列表，或者错误信息。
    """
    try:
        print("[llm_tools.listDiaryFilesTool] Listing diary files in directory:", DIARY_DIR)
        files = os.listdir(DIARY_DIR)
        files=[f for f in files if f.endswith('.txt')]
        return "\n".join(files) if files else "日记目录为空。"
    except Exception as e:
        return f"列出日记文件出错: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def readDiaryFileTool(filename: str) -> str:
    """
    Description:
        读取指定日记文件的内容。
        你可以自行决定何时使用此工具。
    Args:
        filename (str): 需要读取的日记文件名。
    Returns:
        str: 文件内容的字符串表示，或者错误信息。
    """
    file_path=os.path.join(DIARY_DIR,filename)
    try:
        print("[llm_tools.readDiaryFileTool] Reading diary file:", file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"读取日记文件出错: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def writeDiaryFileTool(content: str) -> str:
    """
    Description:
        将指定内容写入日记文件，使用UTF-8编码。
        文件名根据当前日期时间生成，格式为YYYYMMDD_HHMMSS.txt
        你可以自行决定何时使用此工具。
    Args:
        content (str): 需要写入文件的内容字符串。
    Returns:
        str: 写入成功的确认信息，或者错误信息。
    """    
    from datetime import datetime
    now = datetime.now()
    filename = now.strftime("%Y%m%d_%H%M%S") + ".txt"
    file_path=os.path.join(DIARY_DIR,filename)
    try:
        print("[llm_tools.writeDiaryFileTool] Writing to diary file:", file_path)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"日记文件写入成功，文件名为: {filename}"
    except Exception as e:
        return f"写入日记文件出错: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def getCwdTool()->str:
    """获取当前工作目录

    Returns:
        str: 当前工作目录
    """    
    try:
        return os.getcwd()
    except Exception as e:
        return f"出错{str(e)}"
@add_to_tool_list
@tool
@record_func_name
def listDirectoryTool(path: str) -> str:
    """
    Description:
        列出指定目录下的所有文件和子目录。
        这个工具只应该在用户需要时执行。
        如果用户未说明，请勿擅自使用此工具。
    Args:
        path (str): 需要列出的目录路径。
    Returns:
        str: 目录下的文件和子目录列表，或者错误信息。
    """
    #dir commands/ls command
    try:
        print("[llm_tools.listDirectoryTool] Listing directory:", path)
        if os.name == 'nt':  # Windows
            with os.popen(f'dir "{path}"') as f:
                output = f.read()
        else:  # Unix/Linux/Mac
            with os.popen(f'ls "{path}"') as f:
                output = f.read()
        return output if output else "目录为空。"
    except Exception as e:
        return f"列出目录出错: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def readTextFileTool(file_path: str, start_line: int = 1, end_line: int = 0) -> str:
    """
    Description:
        读取指定文本文件的内容（支持按行范围读取）。
        行为与 read_file 风格一致：
        - file_path: 文件路径
        - start_line: 起始行（1-based）
        - end_line: 结束行（含），<=0 表示读到文件末尾
    Args:
        file_path (str): 需要读取的文本文件路径。
        start_line (int): 起始行号（从1开始）。
        end_line (int): 结束行号（包含该行）。
    Returns:
        str: 指定行范围内容，或错误信息。
    """
    try:
        print("[llm_tools.readTextFileTool] Reading file:", file_path)
        return _safe_read_file_range(file_path, int(start_line), int(end_line))
    except Exception as e:
        return f"读取文件出错: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def writeTextFileTool(file_path: str = "", content: str = "", patch_text: str = "") -> str:
    """
    Description:
        修改文件内容，支持两种模式：

        1) Patch 模式（推荐）：
           传入 patch_text，格式与 apply_patch 风格一致，例如：
           *** Begin Patch
           *** Update File: d:/a.txt
           @@
           -old
           +new
           *** End Patch

        2) 覆写模式（向后兼容）：
           传入 file_path + content，直接整文件写入。

    Args:
        file_path (str): 覆写模式下的目标文件路径。
        content (str): 覆写模式下写入内容。
        patch_text (str): Patch 文本。
    Returns:
        str: 写入成功的确认信息，或者错误信息。
    """
    try:
        if patch_text and str(patch_text).strip():
            print("[llm_tools.writeTextFileTool] Applying patch text")
            return _apply_patch_text(patch_text)

        if not file_path:
            return "写入失败：未提供 file_path，或未提供 patch_text。"

        print("[llm_tools.writeTextFileTool] Writing to file:", file_path)
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"文件写入成功: {str(p)}"
    except Exception as e:
        return f"写入文件出错: {str(e)}"

@add_to_tool_list
@tool
@record_func_name
def beepTool(frequency: int, duration: int) -> str:
    """
    Description:
        发出指定频率和持续时间的蜂鸣声。
    Args:
        frequency (int): 蜂鸣声的频率（Hz）。
        duration (int): 蜂鸣声的持续时间（毫秒）。
    Returns:
        str: 结果信息。
    """
    if os.name == 'nt':
        print("[llm_tools.beepTool] Emitting beep sound with frequency:", frequency, "duration:", duration)
        winsound.Beep(frequency, min(duration,3000))
        return "蜂鸣声已发出。"
    else:
        return "蜂鸣声工具仅在Windows系统上可用。"
@add_to_tool_list
@tool
@record_func_name
def musicPlayTool(url: str) -> str:
    """
    Description:
        播放指定URL的音乐。
        会同步口型。
        请注意 如果使用这个工具，则请在正文中一字不差的输出 <NO_TTS_OUTPUT>
    Args:
        url (str): 音乐的URL地址,支持file://和http(s)://等协议。
    Returns:
        str: 结果信息。
    """
    print("[llm_tools.musicPlayTool] Playing music from URL:", url)
    backend2frontend.FrontEndPlayMusic(url)
    return "音乐播放命令已发送到前端。"
@add_to_tool_list
@tool
@record_func_name
def bgPlayTool(url: str) -> str:
    """
    Description:
        播放指定URL的背景音乐。
        播放一次。
        不会同步口型。
    Args:
        url (str): 背景音乐的URL地址,支持file://和http(s)://等协议。
    Returns:
        str: 结果信息。
    """
    print("[llm_tools.bgPlayTool] Playing background music from URL:", url)
    backend2frontend.FrontEndPlayBG(url)
    return "背景音乐播放命令已发送到前端。"


def _resolve_live2d_model_path() -> Path:
    cfg = getattr(conf, "config", {}) or {}
    model_rel = str(cfg.get("LIVE2D_MODEL_PATH", "2D/hiyori_pro_zh/hiyori_pro_t11.model3.json") or "").strip()
    frontend_root = Path(conf.CONFIG_ROOT).parent / "frontend"
    model_path = Path(model_rel)
    if not model_path.is_absolute():
        model_path = frontend_root / model_rel
    return model_path


def _read_model_motion_names(model_path: Path) -> list[str]:
    if not model_path.exists() or not model_path.is_file():
        return []
    try:
        data = json.loads(model_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    motions = (((data or {}).get("FileReferences") or {}).get("Motions") or {})
    if not isinstance(motions, dict):
        return []
    return sorted([str(k) for k in motions.keys() if str(k).strip()])


@add_to_tool_list
@tool
@record_func_name
def listAvailableMotionsTool() -> str:
    """
    Description:
        获取当前 Live2D 模型可用的 Motion 名称列表。
        列表来源于当前配置的 LIVE2D_MODEL_PATH 对应的 model3.json 文件。
    Args:
        None
    Returns:
        str(json): 包含 model_path、motion_count 和 motions。
    """
    try:
        model_path = _resolve_live2d_model_path()
        motions = _read_model_motion_names(model_path)
        payload = {
            "status": "ok",
            "model_path": str(model_path),
            "motion_count": len(motions),
            "motions": motions,
        }
        print("[llm_tools.listAvailableMotionsTool] model=", model_path, "count=", len(motions))
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


@add_to_tool_list
@tool
@record_func_name
def triggerMotionTool(motion_name: str) -> str:
    """
    Description:
        触发指定 Live2D Motion。
    Args:
        motion_name (str): 要触发的 motion 名称，例如 Idle、TapBody。
    Returns:
        str(json): 执行状态与 motion 名称。
    """
    name = str(motion_name or "").strip()
    if not name:
        return json.dumps({"status": "error", "error": "motion_name 不能为空"}, ensure_ascii=False)
    try:
        print("[llm_tools.triggerMotionTool] Trigger motion:", name)
        backend2frontend.frontendSetMotion(name)
        return json.dumps({"status": "ok", "command": "SET_MOTION", "motion": name}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "motion": name}, ensure_ascii=False)

@add_to_tool_list
@tool
@record_func_name
def guiOpTool(command: str) -> str:
    """
    Description:
        执行语言形式的GUI操作命令，并返回结果。
        这个工具只应该在用户需要时执行。
        这会调用一个专用LLM来处理GUI操作。
        你只需清晰简单描述你的需求即可。
        如 “关闭VSCode软件”
    Args:
        command (str): 需要执行的GUI操作命令字符串。
    Returns:
        str: GUI操作的结果字符串，或者错误信息。
    """
    try:
        print("[llm_tools.guiOpTool] Executing GUI operation command:", command)
        result_str=gui_llm_lib.gui_op(command)
        return result_str
    except Exception as e:
        return f"执行GUI操作出错: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def showNimbleWindowTool(html: str, title: str = "灵动交互", recall_text: str = "用户仍在处理这个灵动窗口，请查看用户是否已完成操作。", reminder_interval_seconds: int = 120, lifespan: int = 1800, metadata_json: str = "{}") -> str:
    """
    Description:
        非阻塞地创建一个“灵动交互”窗口，并显示在前端虚拟形象旁边。

        这是处理复杂任务确认、表单填写、选项确认、安装参数收集等场景的核心工具。
        调用后不会阻塞当前对话，也不会等待用户立即完成操作。
        相反，它会：
        1. 在前端显示一个独立的 HTML 窗口；
        2. 自动绑定一个 reminder trigger，周期性提醒你关注该窗口；
        3. 自动绑定一个 result trigger，当用户提交时再次唤醒你；
        4. 自动绑定一个 expire trigger，窗口生命周期结束时自动关闭；
        5. 当窗口被用户关闭或提交后，其关联 trigger 会一并删除。

        你应当在如下情况使用它：
        - 需要用户选择多个选项；
        - 需要用户填写文本/路径/参数；
        - 需要用户确认安装、危险操作、批量操作细节；
        - 纯语音交互效率低、歧义大、确认轮次过多时。
        - 其他需要更丰富的交互方式的任何场景

        前端窗口中的 HTML 可以包含自定义 UI 元素，例如：按钮、复选框、输入框、选择器等。
        你写入的 HTML 中可以直接调用前端注入的 JavaScript API：

        - `window.nimble.submit(data)`
            向后端提交当前窗口结果，并唤醒你继续处理。
        - `window.nimble.close(reason)`
            关闭当前窗口，并清理绑定 trigger。

        这两个 API 会自动关联当前窗口的 callback_id，因此你不需要手动拼接 callback_id。

        HTML 编写建议：
        - 尽量使用内联样式，避免依赖外部资源；
        - 明确写出提示语、确认按钮、取消按钮；
        - 在按钮中调用 `window.nimble.submit({...})` 提交结构化 JSON 结果；
        - 若用户取消，调用 `window.nimble.close('cancelled')`。

        一个常见示例：
        ```html
        <div style="padding:12px; color:#fff;">
          <h3>安装确认</h3>
          <label>安装路径 <input id="installPath" value="D:/Apps/Test" /></label>
          <label><input id="desktopShortcut" type="checkbox" checked /> 创建桌面快捷方式</label>
          <div style="margin-top:12px; display:flex; gap:8px;">
            <button onclick="window.nimble.submit({ action: 'confirm', installPath: document.getElementById('installPath').value, desktopShortcut: document.getElementById('desktopShortcut').checked })">确认</button>
            <button onclick="window.nimble.close('cancelled')">取消</button>
          </div>
        </div>
        ```

        注意：
        - 这是非阻塞工具。调用后你不应假设用户已经给出答案；
        - 真正的结果会通过 trigger 在后续再次唤醒你；
        - 你的后续逻辑应等待由 result/reminder/expire 触发的新上下文，而不是在当前轮强行继续索要结果。

    Args:
        html (str): 要展示在前端窗口中的 HTML 内容。
        title (str): 窗口标题。
        recall_text (str): reminder trigger 唤醒你时附带的提示信息。
        reminder_interval_seconds (int): 窗口打开期间，提醒你关注该窗口的周期秒数。（默认为 120 秒，实际情况中不应短于120s）
        lifespan (int): 窗口生命周期（秒）。到期后窗口及关联 trigger 自动删除。
        metadata_json (str): 额外元数据 JSON 字符串。
    Returns:
        str: 创建结果说明，包含 callback_id。
    """
    if not STARTED:
        return "系统尚未完全启动，无法创建灵动交互窗口。"
    try:
        metadata = json.loads(metadata_json) if metadata_json else {}
        callback_id = nimble.build_callback_id()
        session = nimble.create_nimble_session(
            callback_id,
            title=title,
            html=html,
            recall_text=recall_text,
            reminder_interval_seconds=reminder_interval_seconds,
            lifespan=lifespan,
            metadata=metadata,
        )

        trigger_manager.append_trigger({
            "id": session["result_trigger_id"],
            "type": "event",
            "event_name": "nimble_result",
            "callback_id": callback_id,
            "recall_description": f"灵动窗口 {callback_id} 收到了用户提交结果。",
            "lifespan": lifespan,
        })
        trigger_manager.append_trigger({
            "id": session["reminder_trigger_id"],
            "type": "nimble-reminder",
            "callback_id": callback_id,
            "interval_seconds": reminder_interval_seconds,
            "recall_description": recall_text,
            "lifespan": lifespan,
        })
        from datetime import datetime, timedelta
        trigger_manager.append_trigger({
            "id": session["expire_trigger_id"],
            "type": "nimble-expire",
            "callback_id": callback_id,
            "target": (datetime.now() + timedelta(seconds=lifespan)).isoformat(),
            "recall_description": f"灵动窗口 {callback_id} 已过期。",
            "lifespan": lifespan,
        })
        backend2frontend.FrontEndShowNimbleWindow(nimble.export_window_payload(callback_id))
        return f"灵动交互窗口已创建，callback_id={callback_id}。该窗口为非阻塞式，结果会在后续 trigger 唤醒时返回。"
    except Exception as e:
        return f"创建灵动交互窗口失败: {str(e)}"

@add_to_tool_list
@tool
@record_func_name
def closeNimbleWindowTool(callback_id: str, reason: str = "closed_by_agent") -> str:
    """
    Description:
        主动关闭一个已存在的灵动交互窗口，并清理其关联的 result/reminder/expire trigger。
        当你确认这个窗口已不再需要，或者任务已经结束、用户已取消时，应调用此工具清理资源。
    Args:
        callback_id (str): 需要关闭的灵动窗口 callback_id。
        reason (str): 关闭原因。
    Returns:
        str: 关闭结果。
    """
    try:
        session = nimble.close_nimble_session(callback_id, reason=reason)
        if not session:
            return f"未找到 callback_id={callback_id} 对应的灵动窗口。"
        trigger_manager.delete_trigger(session["result_trigger_id"])
        trigger_manager.delete_trigger(session["reminder_trigger_id"])
        trigger_manager.delete_trigger(session["expire_trigger_id"])
        backend2frontend.FrontEndCloseNimbleWindow({"callback_id": callback_id, "reason": reason})
        nimble.cleanup_nimble_session(callback_id)
        return f"灵动窗口已关闭，callback_id={callback_id}"
    except Exception as e:
        return f"关闭灵动窗口失败: {str(e)}"


@add_to_tool_list
@tool
@record_func_name
def triggerListTool() -> str:
    """
    Description:
        列出当前所有已注册的触发器。
        触发器触发时，会唤醒你。
    Returns:
        str: 触发器列表的字符串表示，或者错误信息。
    """
    if not STARTED:
        return "系统尚未完全启动，无法列出触发器。"
    try:
        print("[llm_tools.triggerListTool] Listing all triggers.")
        return trigger_manager.get_trigger_information()
    except Exception as e:
        return f"列出触发器出错: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def triggerAddTool(trigger_json: str) -> str:
    """
    Description:
        添加一个新的触发器。
        触发器触发时，会唤醒你。
        触发器 JSON 格式说明

        每个 trigger 对象必须满足下列几类之一的模式（多余字段会被拒绝）。

        通用字段（所有类型）

        - id (string) — 触发器唯一标识（用于删除/覆盖）。必须存在且在 store 中唯一。
        - type (string) — 触发器类型，取值："datetime" | "interval" | "py-eval" | "event" | "nimble-reminder" | "nimble-expire"
        - recall_description (string, optional) — 可选的描述/提示，用于回忆或展示
        - lifespan (int, optional) — 生命周期（秒）。超过后触发器自动删除。

        类型一：DateTimeTrigger（一次性时间触发器）

        - type: "datetime"
        - target: datetime 字符串或 ISO 格式（必填）
        - 支持格式示例：
            - "2024-02-28 15:30:00" （"YYYY-MM-DD HH:MM:SS"）
            - "2024-02-28T15:30:00" 或者带时区："2024-02-28T15:30:00+08:00"（ISO）
            行为：
        - 当系统时间 >= target 时触发，触发后自动从 store 中移除（一次性）。

        示例：

        ```json
        {
        "id": "buy_coffee_reminder",
        "type": "datetime",
        "target": "2026-01-31 09:00:00",
        "recall_description": "上午买咖啡"
        }
        ```

        类型二：IntervalTrigger（周期触发器）

        - type: "interval"
        - interval_seconds: integer >= 1（必填） — 周期秒数
        - last_triggered: float（可选） — 上次触发的时间戳（UNIX 时间，秒）。若缺失，系统会使用默认值（创建时设置为当前时间）。
        行为：
        - 当 (now - last_triggered) >= interval_seconds 时触发，触发后会更新 last_triggered 并保存到文件以保证下次计算正确。

        示例：

        ```json
        {
        "id": "hourly_status_check",
        "type": "interval",
        "interval_seconds": 3600,
        "recall_description": "每小时检查状态"
        }
        ```

        类型三：PyEvalTrigger（基于表达式的触发器）

        - type: "py-eval"
        - eval_code: string（必填） — Python 表达式或语句，返回值用于决定是否触发（truthy 则触发）
        行为与风险：
        - 每轮轮询会 eval(eval_code)。如果表达式结果为 True（或 truthy），触发一次（每轮会继续评估，未改变 last_triggered 行为）。

        示例：

        ```json
        {
        "id": "disk_space_low_check",
        "type": "py-eval",
        "eval_code": "import shutil; shutil.disk_usage('/').free < 10 * 1024 * 1024 * 1024",
        "recall_description": "磁盘可用空间低于 10GB 时触发"
        }
        ```
        类型四：EventTrigger（事件触发器）

        - type: "event"
        - event_name: string（必填）
        - callback_id: string（可选，nimble 常用）
        - payload: object（可选）

        类型五：NimbleRemindTrigger（灵动窗口提醒触发器）

        - type: "nimble-reminder"
        - callback_id: string（必填）
        - interval_seconds: integer >= 1（必填）

        类型六：NimbleExpireTrigger（灵动窗口过期触发器）

        - type: "nimble-expire"
        - callback_id: string（必填）
        - target: datetime 字符串（必填）

        请严格遵守上述格式添加触发器，确保字段完整且类型正确。
    Args:
        trigger_json (str): 触发器的JSON字符串表示。
    Returns:
        str: 添加结果的确认信息，或者错误信息。
    """
    if not STARTED:
        return "系统尚未完全启动，无法操作触发器。"
    try:
        print("[llm_tools.triggerAddTool] Adding new trigger with JSON:", trigger_json)
        trigger_manager.append_trigger(trigger_json)
        return f"触发器添加成功"
    except Exception as e:
        return f"添加触发器出错: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def triggerRemoveTool(trigger_id: str) -> str:
    """
    Description:
        移除指定ID的触发器。
    Args:
        trigger_id (str): 需要移除的触发器ID。
    Returns:
        str: 移除结果的确认信息，或者错误信息。
    """
    if not STARTED:
        return "系统尚未完全启动，无法操作触发器。"
    try:
        print("[llm_tools.triggerRemoveTool] Removing trigger with ID:", trigger_id)

        trigger_manager.delete_trigger(trigger_id)
        return f"触发器移除成功，ID: {trigger_id}"
    except Exception as e:
        return f"移除触发器出错: {str(e)}"


@add_to_tool_list
@tool
@record_func_name
def ragQueryTool(query: str, mode: str = "hybrid", only_need_context: bool = True) -> str:
    """
    Description:
        同步（阻塞式）执行一次 RAG 查询(查询目标：你的对话记录和相关文档)，并直接返回结果。
        默认只返回检索到的相关内容，不让模型总结。
        本工具会接入文档管理器，用于确保 RAG 文档跟踪器已初始化并可用。
            
    Args:
        query (str): 要查询的问题或关键词。
        mode (str): 检索模式，可选 naive/local/global/hybrid/mix。（默认 hybrid）
        only_need_context (bool): 是否只返回检索上下文。默认 True。
    Returns:
        str: RAG 查询结果，或错误信息。
    """
    try:
        _ = RAG_TRACKER
        return asyncio.run(
            rag_client.rag_query(
                query,
                mode=mode,
                only_need_context=only_need_context,
                enable_rerank=False,
            )
        )
    except Exception as e:
        return f"RAG 同步查询失败: {str(e)}"


@add_to_tool_list
@tool
@record_func_name
async def ragQueryAsyncStartTool(query: str, mode: str = "hybrid", only_need_context: bool = True) -> str:
    """
    Description:
        启动一个异步 RAG 查询任务，立即返回 rag_callback_id，不阻塞当前对话。
        查询完成后会通过 Trigger System 再次唤醒你。
        被唤醒后，请调用 ragQueryAsyncGetTool(callback_id) 获取实际查询结果。
        默认只返回检索到的相关内容，不让模型总结。
    Args:
        query (str): 要查询的问题或关键词。
        mode (str): 检索模式，可选 naive/local/global/hybrid/mix。
        only_need_context (bool): 是否只返回检索上下文。默认 True。
    Returns:
        str: 启动结果说明，包含 rag_callback_id。
    """
    try:
        _ = RAG_TRACKER
        callback_id = f"ragcb_{uuid.uuid4().hex}"
        _store_rag_async_result(callback_id, {
            "status": "running",
            "callback_id": callback_id,
            "query": query,
            "mode": mode,
            "only_need_context": only_need_context,
            "started_at": time.time(),
        })
        _run_async_in_thread(_rag_query_async_job(callback_id, query, mode, only_need_context))
        return (
            f"RAG 异步查询已启动，rag_callback_id={callback_id}。"
            f"完成后会通过 Trigger System 唤醒你；届时请调用 ragQueryAsyncGetTool 获取结果。"
        )
    except Exception as e:
        return f"启动 RAG 异步查询失败: {str(e)}"


@add_to_tool_list
@tool
@record_func_name
def ragQueryAsyncGetTool(rag_callback_id: str) -> str:
    """
    Description:
        获取一个已启动的异步 RAG 查询结果。
        当 ragQueryAsyncStartTool 启动异步查询后，会先返回 rag_callback_id；
        查询完成并通过 trigger 唤醒你后，请使用本工具按 callback_id 获取结果。
    Args:
        rag_callback_id (str): 异步 RAG 查询的回调 ID。
    Returns:
        str: 查询结果、运行中状态或错误信息。
    """
    try:
        result = _get_rag_async_result(rag_callback_id)
        if result is None:
            return f"未找到 rag_callback_id={rag_callback_id} 对应的异步查询任务。"
        status = result.get("status", "unknown")
        if status == "running":
            return f"RAG 异步查询仍在运行中，rag_callback_id={rag_callback_id}。请稍后再试。"
        if status == "error":
            return f"RAG 异步查询失败，rag_callback_id={rag_callback_id}，错误：{result.get('error', 'unknown error')}"
        return str(result.get("result", ""))
    except Exception as e:
        return f"获取 RAG 异步查询结果失败: {str(e)}"
@add_to_tool_list
@tool
@record_func_name
def ragDeclareFileUpdateTool(file_path:str)->str:
    """用于将一个文件加入RAG系统的更新声明工具。当你修改了某个文件的内容，并希望 RAG 系统能够尽快地将这个更新纳入检索范围时，可以调用此工具声明文件已更新。

    Args:
        file_path (str): 要加入RAG系统的文件绝对路径。

    Returns:
        str: 结果说明

    注意：
        这个工具是非阻塞工具。调用后你不应假设文件已经被处理完成；
    """    
    try:
        _run_async_in_thread(RAG_TRACKER.declareUpdateDoc(file_path))
        return f"已声明文件更新，路径: {file_path}。\nRAG系统会尽快处理这个更新，但请注意这是一个非阻塞操作，文件可能尚未被完全处理。"
    except Exception as e:
        return f"声明文件更新失败: {str(e)}"


@add_to_tool_list
@tool
@record_func_name
def minecraftCommandTool(command_json: str) -> str:
    """
    Description:
        向 Minecraft 操作系统发送一条 JSON 命令，并返回执行结果。
        这是 FaustBot 操作 Minecraft 的主入口工具。
    Args:
        command_json (str): JSON 格式命令，例如 {"name":"get-mobs-around","args":{"radius":5}}
    Returns:
        str(json): 执行结果 JSON。
    """
    try:
        payload = json.loads(command_json)
        name = payload.get("name")
        args = payload.get("args") or {}
        if not name:
            return json.dumps({"ok": False, "error": "missing command name"}, ensure_ascii=False)
        result = asyncio.run(minecraft_client.send_command(name, args))
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@add_to_tool_list
@tool
@record_func_name
def minecraftConnectTool(host: str, port: int, username: str, version: str = "") -> str:
    """
    Description:
        连接到 Minecraft 服务器。Agent 应自行决定何时加入服务器。
    Args:
        host (str): 服务器地址。
        port (int): 服务器端口。
        username (str): Bot 用户名。
        version (str): 可选协议版本。
    Returns:
        str(json): 连接结果。
    """
    try:
        result = asyncio.run(minecraft_client.connect_server(host, port, username, version or None))
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@add_to_tool_list
@tool
@record_func_name
def minecraftStatusTool() -> str:
    """
    Description:
        获取当前 Minecraft Bot 状态，包括连接、坐标、血量、饱食度和附近实体等。
    Args:
        None
    Returns:
        str(json): Bot 状态 JSON。
    """
    try:
        result = asyncio.run(minecraft_client.get_status())
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@add_to_tool_list
@tool
@record_func_name
def minecraftDisconnectTool(reason: str = "disconnect requested") -> str:
    """
    Description:
        断开当前 Minecraft 服务器连接。
    Args:
        reason (str): 断开原因。
    Returns:
        str(json): 断开结果 JSON。
    """
    try:
        result = asyncio.run(minecraft_client.disconnect_server(reason))
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@add_to_tool_list
@tool
@record_func_name
async def installOpenClawSkillTool(slug: str, overwrite: bool = False) -> str:
    """
    Description:
        安装一个 OpenClaw Skill 到当前 Agent 的独立目录 agents/<agent>/skill.d/<slug>。
        安装前会触发前端 HIL 确认框，用户批准后才会真正下载与安装。
        下载 API:
        https://wry-manatee-359.convex.site/api/v1/download?slug=<NAME>

        Skill ZIP 结构要求：
        - _meta.json
        - SKILL.md
        - 其他文件
    Args:
        slug (str): skill 名称（slug）。
        overwrite (bool): 若已存在是否覆盖安装。
    Returns:
        str: 安装结果说明。
    """
    if not STARTED:
        return "系统尚未完全启动，无法安装 skill。"

    slug = str(slug or "").strip()
    if not slug:
        return "安装失败：slug 不能为空。"

    approved, reason = await HILRequest(
        id=f"skill_install_{uuid.uuid4().hex}",
        title=f"允许安装 Skill: {slug} ?",
        summary=(
            f"Agent 请求安装 Skill：{slug}\n"
            f"目标目录: agents/{conf.AGENT_NAME}/skill.d/{slug}\n"
            f"来源: https://wry-manatee-359.convex.site/api/v1/download?slug={slug}\n"
            f"overwrite={bool(overwrite)}"
        ),
    )
    if not approved:
        return f"用户拒绝安装 Skill，slug={slug}，原因={reason}"

    try:
        result = await asyncio.to_thread(_install_skill_from_slug, slug, overwrite)
        return f"Skill 安装成功: {json.dumps(result, ensure_ascii=False)}"
    except Exception as e:
        return f"Skill 安装失败: {str(e)}"

if __name__ == "__main__":
    for tool in toollist:
        print(f"Tool name: {tool.name},\nDescription: {tool.description}")