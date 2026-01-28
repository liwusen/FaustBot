import json
import os
from typing import Any, Dict
p_join=os.path.join
d_name=os.path.dirname
a_path=os.path.abspath
CONFIG_ROOT=d_name(d_name(a_path(__file__)))
CONFIG_FILE_P_PATH = p_join(CONFIG_ROOT, 'faust.config.private.json')
CONFIG_FILE_PATH= p_join(CONFIG_ROOT, 'faust.config.json')
with open(CONFIG_FILE_P_PATH, 'r', encoding='utf-8') as f:
    private_config = json.load(f)
    DEEPSEEK_API_KEY = private_config.get('DEEPSEEK_API_KEY', '')
    SEARCH_API_KEY = private_config.get('SEARCH_API_KEY', '')