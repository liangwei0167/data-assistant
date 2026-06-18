"""数据助手 - AI配置模块"""

from typing import Optional, Union

""" 变量类型注解"""
model_name: str = "deepseek_chat"
max_tokens: int = 4096
temperature: float = 0.7
use_streaming: bool = True
api_key: Optional[str] = None

""" 函数类型注解"""
def create_config(
     model: str,
     api_key: int,
     temperature: float = 0.7,
     max_tokens: int = 4096,
) -> dict:
    config: dict = {
        "model": model,
        "api_key": api_key,
        "temperature": temperature,  
        "max_tokens": max_tokens,
    }
    return config

def get_model_info(model: str) -> dict[str, Union[str, int]]:
    info: dict[str, Union[str, int]] = {
        "name": model,
        "provider": "deepseek",
        "context_window": 128000,
    }
    return info


