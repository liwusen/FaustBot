#LLM Security Manager
import os.path
from fnmatch import fnmatch
import asyncio
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import json,re
import faust_backend.config_loader as conf
checker_agent=ChatOpenAI(model=conf.SECURITY_VERIFIER_LLM_MODEL,
                         base_url=conf.SECURITY_VERIFIER_LLM_API_ENDPOINT,
                         api_key=conf.SERCURITY_VERIFIER_LLM_KEY,
                         )
def setSecurityLevel(level):
    """设置安全级别

    Args:
        level (str): 安全级别
            可选值：
            - "unlimited": 无限制，允许执行任何操作
            - "loose": 宽松，允许执行大部分操作，但会进行子LLM审核
            - "standard": 标准，允许执行常见操作，限制访问路径
            - 'strict': 严格，禁止执行敏感操作
            - 'disabled': 禁用，禁止执行任何系统操作
    """
    security_config['level'] = level

security_config = {
    'level': 'standard',
    'dirs':{
        "*/agents/*":"full",
        "*/agents/*/AGENT.md":"read",

    }
}
"""
ACCESS LEVELS:
- "full":完全控制
- "read":只读访问
- "deny":完全禁止访问
- "full-no-rm":禁止删除
- "none":任何操作都需要人工审批
"""
async def match_path_pattern(path, pattern):
    """匹配路径模式，支持通配符*"""
    path = os.path.normpath(path).replace("\\", "/")
    pattern = os.path.normpath(pattern).replace("\\", "/")
    return fnmatch(path, pattern)
async def check_access(path, operation):
    """检查访问权限

    Args:
        path (str): 访问的文件路径
        operation (str): 操作类型，如 "read", "write", "delete"
    
    Returns:
        bool: 是否允许访问
    """
    level = security_config['level']
    if level == 'unlimited':
        print(f"安全检查: 路径={path}, 操作={operation}, 访问级别={level} -> 允许")
        return True
    elif level == 'disabled':
        print(f"安全检查: 路径={path}, 操作={operation}, 访问级别={level} -> 禁止")
        return False
    
    # 根据路径模式匹配访问权限
    for pattern, access in security_config['dirs'].items():
        if await match_path_pattern(path, pattern):
            if access == 'full':
                print(f"安全检查: 路径={path}, 操作={operation}, 访问级别={access} -> 允许")
                return True
            elif access == 'read' and operation == 'read':
                print(f"安全检查: 路径={path}, 操作={operation}, 访问级别={access} -> 允许")
                return True
            elif access == 'full-no-rm' and operation != 'delete':
                print(f"安全检查: 路径={path}, 操作={operation}, 访问级别={access} -> 允许")
                return True
    # 需要人工审批，调用子LLM进行审核
    try:
        if os.path.isdir(path):
            dirlist=os.listdir(path)
            dirlist_str="目录子内容列表"+"\n".join(dirlist)
        else:
            dirlist_str=""
        approval = await checker_agent.ainvoke([
            HumanMessage(
                content=f"""
                请审核以下操作是否安全：
                路径={path}, 操作={operation}。请只回复 approve 或 reject。注意，你只对操作的安全性进行判断，不要考虑其他因素。
                不安全的操作包括但不限于：
                - 对敏感文件（密码，Token）的访问
                - 大规模删除或修改操作
                - 其他可能导致系统不稳定或数据泄露的操作
                安全的操作包括但不限于：
                - 读取公共文件
                - 对非敏感文件的修改
                - 删除指定的少量文件
                - 其他对系统影响较小的操作
                请根据以上原则进行判断，并回复 approve 或 reject。
                {dirlist_str}
                """
            )
        ])
        decision = (approval.content or "").strip().lower()
        print(f"安全检查: 路径={path}, 操作={operation}, 访问级别=none -> 需要人工审批，模型返回={decision}")
        return decision == 'approve'
    except Exception as e:
        print(f"安全检查: 路径={path}, 操作={operation}, 访问级别=none -> 审批失败，默认拒绝。错误={e}")
        return False
async def extract_command_information(command:str):
    """从命令中提取路径和操作信息，供安全检查使用"""
    prompt="""
    你是一个安全检查助手.
    请从以下命令中提取路径和操作信息，并进行安全检查，供安全检查使用。命令格式可能多样，请尽量准确解析出路径和操作类型。
    危险的命令:
    - 大规模删除文件：rm -rf .
    - 读取敏感文件：cat ./TOKEN.txt
    - 修改敏感文件：echo "new_token" > ./TOKEN.txt
    - 修改系统设置：sysctl -w key=value
    安全的命令:
    - 正常文件操作(增删查改)
    - 写入正常的文件
    - 读取公共文件
    - 修改公共文件
    - 重定向输出到非敏感文件
    需要人工审批的命令:
    - 卸载软件
    - 删除文件
    - 修改系统设置
    - 其他可能存在风险且容易造成较大影响的操作
    如果你认为某个操作可能存在安全风险，但不确定是否危险，可以回复 human_approval_needed，表示需要人工审批.
    同时,你需要同意所有安全的命令，并拒绝所有危险的命令。
    如果你确实无法判断命令的安全性，可以回复 human_approval_needed，表示需要人工审批。
    命令示例：
    1. 删除文件：rm -rf /path/to/file
    返回格式（JSON序列化）:
    不要使用任何解释性的文本,Markdown 等,直接返回JSON对象，格式如下：
    {
        "accept":"是否批准该操作，approve或reject或human_approval_needed(需要人工审批)",
        "reason":"原因",
        "paths":[
            {
                "path": "文件路径1",
                "operation": "操作类型: read, write, delete"
            },
            {
                "path": "文件路径2",
                "operation": "操作类型: read, write, delete"
            }
            (省略...)
        ]
    }
    示例输入:
    rm -rf /path/to/file
    示例输出:
    {
        "accept": "reject",
        "reason": "删除操作过于危险，拒绝执行",
        "paths": [
            {
                "path": "/path/to/file",
                "operation": "delete"
            }
        ]
    }
    
    指令正文
    指令:"""+command
    result = await checker_agent.ainvoke([
        HumanMessage(content=prompt)
    ])
    raw_content = result.content if isinstance(result.content, str) else json.dumps(result.content, ensure_ascii=False)
    cleaned = raw_content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()

    result_json=json.loads(cleaned)
    print(f"从命令中提取的信息: {result_json}")
    accept = str(result_json.get("accept", "reject")).strip().lower()
    paths = result_json.get("paths", [])
    normalized_paths = []
    for item in paths:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path", "")).strip()
        raw_operation = str(item.get("operation", "")).strip()
        raw_operation = re.sub(r"^操作类型\s*[:：]\s*", "", raw_operation, flags=re.IGNORECASE)
        operations = [op.strip().lower() for op in re.split(r"[,，]", raw_operation) if op.strip()]
        normalized_paths.append({
            "path": raw_path,
            "operation": operations if len(operations) > 1 else (operations[0] if operations else "")
        })
        reason=result_json.get("reason", "")
    return accept, normalized_paths, reason
async def demo():
    print(fnmatch("agents/agent1/AGENT.md", "*/agents/*/AGENT.md"))  
    setSecurityLevel("standard")
    # print(await check_access("x/agents/agent1/AGENT.md", "read"))  # True
    # print(await check_access("x/agents/agent1/AGENT.md", "write")) # False
    # print(await check_access("x/agents/agent1/script.py", "write")) # True
    # print(await check_access("D:/ALLEN/", "delete")) # False

    print(await extract_command_information("rm -rf /"))
    print(await extract_command_information("cat hello.txt > foo.txt"))
    print(await extract_command_information("echo 'Hello World' > /tmp/hello.txt"))
    print(await extract_command_information("cat /etc/passwd"))
    print(await extract_command_information("sudo apt uninstall testpackage"))
if __name__ == "__main__":
    # 示例用法
    asyncio.run(demo())