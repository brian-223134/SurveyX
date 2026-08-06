import os
import json
import logging
import re
import ast
from pathlib import Path
from collections import defaultdict
from typing import List, Tuple, Union, Dict

from src.configs.logger import get_logger

logger = get_logger("src.modules.utils")


def shut_loggers():
    for logger in logging.Logger.manager.loggerDict:
        logging.getLogger(logger).setLevel(logging.INFO)


def sanitize_filename(filename: str) -> str:
    return re.sub(r'[\\/:"*?<>|]', "_", filename)


def save_result(result: str, path: Union[str, Path]) -> None:
    """문자열을 파일로 저장한다. 상위 디렉터리가 없으면 생성한다.

    Args:
        result (str): 저장할 문자열.
        path (str): 이 문자열을 저장할 위치.
    """
    if isinstance(path, str):
        path = Path(path)
    directory = path.parent
    # 디렉터리가 없으면 생성
    if not directory.exists():
        directory.mkdir(exist_ok=True, parents=True)
    # 파일에 기록
    with path.open("w", encoding="utf-8") as fw:
        fw.write(result)


def load_file_as_string(path: Union[str, Path]) -> str:
    if isinstance(path, str):
        with open(path, "r", encoding="utf-8") as fr:
            return fr.read()
    elif isinstance(path, Path):
        with path.open("r", encoding="utf-8") as fr:
            return fr.read()
    else:
        raise ValueError(path)


def update_config(dic: dict, config_path: str):
    """설정 파일을 갱신한다.

    Args:
        dic (dict): 새 설정 딕셔너리.
    """
    config_path = Path(config_path)
    if config_path.exists():
        config: dict = json.load(open(config_path, "r", encoding="utf-8"))
        config.update(dic)
    else:
        config: dict = dic
    save_result(json.dumps(config, indent=4), config_path)


def save_as_json(result: dict, path: str):
    """
    결과를 JSON 파일로 저장한다.
    """
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=4)


def load_meta_data(dir_path):
    """
    디렉터리 안의 모든 JSON 파일을 불러온다.
    """
    data = []
    for filename in os.listdir(dir_path):
        if filename.endswith(".json"):
            file_path = os.path.join(dir_path, filename)
            with open(file_path, "r", encoding="utf-8") as file:
                result = json.load(file)  # JSON 파일 내용을 Python 리스트로 읽기
            data.append(result)
    return data


def load_single_file(file_path):
    """
    경로를 기준으로 단일 JSON 파일을 불러온다.
    """
    # 파일 경로 존재 여부 확인
    if not os.path.exists(file_path):
        return ""

    # 경로가 존재하면 파일을 열어 읽기
    with open(file_path, "r") as file:
        article = json.load(file)
    return article


def load_prompt(filename: str, **kwargs) -> str:
    """
    prompt 템플릿을 읽어온다.
    """
    path = os.path.join("", filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().format(**kwargs)
    else:
        logger.error(f"Prompt template not found at {path}")
        return ""


Clean_patten = re.compile(pattern=r"```(json|latex)?", flags=re.DOTALL)


def clean_chat_agent_format(content: str):
    content = re.sub(Clean_patten, "", content)
    return content


def load_papers(paper_dir_path_or_papers: Union[Path, List[Dict]]) -> list[dict]:
    if isinstance(paper_dir_path_or_papers, Path):
        papers = []
        for file in os.listdir(paper_dir_path_or_papers):
            file_path = paper_dir_path_or_papers / file
            if file_path.is_dir():
                file_path = file_path / os.listdir(file_path)[0]
            if not file_path.is_file():
                logger.error(f"loading paper error: {file_path} is not a file.")
                continue
            paper = json.loads(load_file_as_string(file_path))
            papers.append(paper)
        return papers
    elif isinstance(paper_dir_path_or_papers, list):
        return paper_dir_path_or_papers
    else:
        raise ValueError()


def load_file_as_text(file_path: Path):
    with file_path.open("r", encoding="utf-8") as fr:
        return fr.read()
