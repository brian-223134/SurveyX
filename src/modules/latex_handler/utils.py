# latex_table_builder.py에서 사용

from collections import defaultdict
import json
import os
import re
from typing import List, Tuple
from rapidfuzz import process
from src.configs.logger import get_logger

logger = get_logger("latex_handler.utils")


def load_all_papers(dir_path: str) -> list[dict]:
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


def fuzzy_match(text: str, candidates: list[str]) -> Tuple[str, int]:
    """`candidates` 리스트에서 `text`와 가장 유사한 텍스트를 선택한다."""
    closest_text, score, idx = process.extractOne(text, candidates)
    return closest_text, idx
