import aiohttp
from typing import Any, Dict


DEFAULT_RAG_BASE_URL = "http://127.0.0.1:18080"


async def rag_health(base_url: str = DEFAULT_RAG_BASE_URL) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{base_url}/health") as response:
            response.raise_for_status()
            return await response.json()


async def rag_insert(text: str, base_url: str = DEFAULT_RAG_BASE_URL) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base_url}/insert", json={"text": text}) as response:
            response.raise_for_status()
            return await response.json()


async def rag_query(query: str, mode: str = "hybrid", base_url: str = DEFAULT_RAG_BASE_URL) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{base_url}/query",
            json={"query": query, "mode": mode},
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return str(payload.get("answer", ""))
async def demo():
    print("Checking RAG health...")
    health = await rag_health()
    print("RAG Health:", health)

    print("\nInserting text into RAG...")
    insert_result = await rag_insert("这是一些测试文本，用于验证 RAG 的插入功能。")
    print("Insert Result:", insert_result)

    print("\nQuerying RAG...")
    answer = await rag_query("测试文本是什么？")
    print("RAG Answer:", answer)
if __name__ == "__main__":
    import asyncio
    asyncio.run(demo())