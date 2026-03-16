@echo on
chcp 65001
echo "开始安装LIGHTRAG"
pause
cd %dp0
mkdir lightrag
cd lightrag
echo "正在安装 LightRAG 依赖项..."


conda deactivate

python -m venv .venv
.venv\Scripts\activate
pip install "lightrag-hku[api]"

cd lightrag_webui
bun install --frozen-lockfile
bun run build
cd ..


cp env.example .env
lightrag-server