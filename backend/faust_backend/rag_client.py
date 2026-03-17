import asyncio
import json
import hashlib
from typing import Any, Dict
from urllib import request
from pathlib import Path
try:
    import config_loader as conf
except ImportError:
    import faust_backend.config_loader as conf
import aiohttp
import pathlib
import time
DEFAULT_RAG_BASE_URL = "http://127.0.0.1:18080"

class docTracker():
    """
        Document Tracker for RAG
        自动在模型创建文件时记录文件路径和关联的文档ID，方便后续查询和管理。
        记录模型生成的文件md5值、当前文件路径、关联的文档ID、创建时间和更新时间等信息。
        如果md5变化，自动更新关联的文档ID和文件路径，确保RAG中的文档与实际文件保持一致。
    """
    class DocInfo:
        def __init__(self, doc_id: str, file_path: str, md5: str, create_time: float, update_time: float):
            self.doc_id = doc_id
            self.file_path = file_path
            self.md5 = md5
            self.create_time = create_time
            self.update_time = update_time
    datafile:str=Path(conf.AGENT_ROOT) / "rag_doc_tracker.json"
    mem_record_file:str=Path(conf.AGENT_ROOT) / "rag_chat_history_records.json"
    verbosity:bool=False
    def __init__(self):
        self.doc_info_map: Dict[str, docTracker.DocInfo] = {}
        self._load_from_file()
    
    def _to_dict(self) -> Dict[str, Dict[str, Any]]:
        return {
            file_path: {
                "doc_id": info.doc_id,
                "file_path": info.file_path,
                "md5": info.md5,
                "create_time": info.create_time,
                "update_time": info.update_time,
            }
            for file_path, info in self.doc_info_map.items()
        }

    def _load_from_file(self):
        if Path(self.datafile).exists():
            with open(self.datafile, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                for file_path, info in data.items():
                    self.doc_info_map[file_path] = docTracker.DocInfo(
                        doc_id=info["doc_id"],
                        file_path=info["file_path"],
                        md5=info["md5"],
                        create_time=info["create_time"],
                        update_time=info["update_time"],
                    )
        else:
            self._save_to_file()
    async def clear_not_exist_docs(self):
        to_delete = []
        for file_path, doc_info in self.doc_info_map.items():
            if not Path(file_path).exists():
                to_delete.append((file_path, doc_info.doc_id))
        for file_path, doc_id in to_delete:
            await rag_delete_document(doc_id)
            del self.doc_info_map[file_path]
            if self.verbosity:
                print(f"[RAG Tracker] Deleted document for non-existent file {file_path} with doc_id {doc_id}")
        if to_delete:
            self._save_to_file()
    async def declareUpdateDoc(self,file_path:str,dry_run:bool=False):
        now_time = time.time()
        file_text = Path(file_path).read_text(encoding="utf-8")
        md5 = hashlib.md5(Path(file_path).read_bytes()).hexdigest()
        if file_path in self.doc_info_map:
            doc_info = self.doc_info_map[file_path]
            if doc_info.md5 != md5:
                doc_info.doc_id = pathlib.Path(file_path).name+"_"+str(int(now_time))
                doc_info.file_path = file_path
                doc_info.md5 = md5
                doc_info.update_time = now_time
            if not dry_run:
                await rag_delete_document(doc_info.doc_id)
                await rag_insert_document(file_text, doc_id=doc_info.doc_id, file_path=file_path)
                if self.verbosity:
                    print(f"[RAG Tracker] Updated document for {file_path} with doc_id {doc_info.doc_id}")
        else:
            new_doc_id = pathlib.Path(file_path).name+"_"+str(int(now_time))
            self.doc_info_map[file_path] = docTracker.DocInfo(new_doc_id, file_path, md5, now_time, now_time)
            if not dry_run:
                await rag_insert_document(file_text, doc_id=self.doc_info_map[file_path].doc_id, file_path=file_path)
            if self.verbosity:
                print(f"[RAG Tracker] Inserted new document for {file_path} with doc_id {self.doc_info_map[file_path].doc_id}")
        self._save_to_file()
    async def new_chat_history_part(self,text):
        now_time = time.time()
        await rag_insert_document(text, doc_id="__CHAT_HISTORY__"+(doc_id:=str(int(now_time))), file_path="__MEM__")
        record = {
            "text": text,
            "timestamp": now_time,
            "doc_id": doc_id,
        }
        if Path(self.mem_record_file).exists():
            with open(self.mem_record_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []
        data.append(record)
        with open(self.mem_record_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    async def clear_chat_history(self):
        if Path(self.mem_record_file).exists():
            with open(self.mem_record_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for record in data:
                doc_id = record.get("doc_id")
                if doc_id:
                    await rag_delete_document(doc_id)
            Path(self.mem_record_file).unlink()
        else:
            if self.verbosity:
                print("[RAG Tracker] No chat history records to clear.")
    def _save_to_file(self):
        with open(self.datafile, "w", encoding="utf-8") as f:
            json.dump(self._to_dict(), f, ensure_ascii=False, indent=4)

async def _json_request(method: str, url: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if aiohttp is not None:
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, json=payload) as response:
                response.raise_for_status()
                return await response.json()

    def _sync_request() -> Dict[str, Any]:
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method=method)
        with request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))

    return await asyncio.to_thread(_sync_request)


async def rag_health(base_url: str = DEFAULT_RAG_BASE_URL) -> Dict[str, Any]:
    return await _json_request("GET", f"{base_url}/health")


async def rag_insert(text: str, base_url: str = DEFAULT_RAG_BASE_URL) -> Dict[str, Any]:
    return await _json_request("POST", f"{base_url}/insert", {"text": text})


async def rag_insert_document(
    text: str,
    *,
    base_url: str = DEFAULT_RAG_BASE_URL,
    doc_id: str | None = None,
    file_path: str | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"text": text}
    if doc_id is not None:
        payload["doc_id"] = doc_id
    if file_path is not None:
        payload["file_path"] = file_path
    return await _json_request("POST", f"{base_url}/insert", payload)


async def rag_list_documents(base_url: str = DEFAULT_RAG_BASE_URL) -> Dict[str, Any]:
    return await _json_request("GET", f"{base_url}/documents")


async def rag_get_documents_by_track_id(track_id: str, base_url: str = DEFAULT_RAG_BASE_URL) -> Dict[str, Any]:
    return await _json_request("GET", f"{base_url}/documents/track/{track_id}")


async def rag_delete_document(doc_id: str, base_url: str = DEFAULT_RAG_BASE_URL) -> Dict[str, Any]:
    return await _json_request("DELETE", f"{base_url}/documents/{doc_id}")


async def rag_config(
    *,
    base_url: str = DEFAULT_RAG_BASE_URL,
    api_key: str | None = None,
    model_base_url: str | None = None,
    chat_model: str | None = None,
    embed_model: str | None = None,
    embed_dim: int | None = None,
    embed_max_token_size: int | None = None,
) -> Dict[str, Any]:
    payload = {
        "api_key": api_key,
        "base_url": model_base_url,
        "chat_model": chat_model,
        "embed_model": embed_model,
        "embed_dim": embed_dim,
        "embed_max_token_size": embed_max_token_size,
    }
    clean_payload = {k: v for k, v in payload.items() if v is not None}
    return await _json_request("POST", f"{base_url}/config", clean_payload)


async def rag_query(
    query: str,
    mode: str = "hybrid",
    *,
    base_url: str = DEFAULT_RAG_BASE_URL,
    only_need_context: bool = False,
    response_type: str = "Multiple Paragraphs",
    enable_rerank: bool = False,
) -> str:
    payload = await _json_request(
        "POST",
        f"{base_url}/query",
        {
            "query": query,
            "mode": mode,
            "only_need_context": only_need_context,
            "response_type": response_type,
            "enable_rerank": enable_rerank,
        },
    )
    return str(payload.get("answer", ""))
async def demo():
    print("Checking RAG health...")
    health = await rag_health()
    print("RAG Health:", health)

    print("\nInserting text into RAG...")
    insert_result = await rag_insert_document("这是一些测试文本，用于验证 RAG 的插入功能。")
    print("Insert Result:", insert_result)

    print("\nListing RAG documents...")
    documents = await rag_list_documents()
    print("Documents:", documents)

    print("\nQuerying RAG context directly...")
    answer = await rag_query("测试文本是什么？", only_need_context=True)
    print("RAG Answer:", answer)
if __name__ == "__main__":
    asyncio.run(demo())