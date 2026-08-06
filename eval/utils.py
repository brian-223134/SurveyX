import json
from pathlib import Path
from typing import Union

import requests


MODEL = "gpt-4o-mini"
URL = "your url here" # 예: "https://api.openai.com/v1/chat/completions"
TOKEN = "your key here" # 예: "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


def remote_chat(
    text_content: str,
    temperature: float = 0.5,
    debug: bool = False,
) -> str:
    """원격 LLM과 대화하고 결과를 반환한다."""
    url = URL
    header = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
    # 텍스트 콘텐츠
    messages = [{"role": "user", "content": text_content}]
    payload = {"model": MODEL, "messages": messages, "temperature": temperature}

    response = requests.post(url, headers=header, json=payload)
    response.raise_for_status()

    try:
        res = json.loads(response.text)
        res_text = res["choices"][0]["message"]["content"]
    except Exception as e:
        res_text = f"Error: {e}"

    if debug:
        return res_text, response
    return res_text

def load_file_as_string(path: Union[str, Path]) -> str:
    if isinstance(path, str):
        with open(path, "r", encoding="utf-8") as fr:
            return fr.read()
    elif isinstance(path, Path):
        with path.open("r", encoding="utf-8") as fr:
            return fr.read()
    else:
        raise ValueError(path)

