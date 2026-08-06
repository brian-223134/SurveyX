"""
@Reference:
1. llama index 템플릿 생성 방법: https://blog.csdn.net/lovechris00/article/details/137782020
"""

import json
import os
import re
import random as normalrandom
from pathlib import Path

from typing import List, Union, Dict
from tqdm import tqdm
from llama_index.core import ChatPromptTemplate, PromptTemplate

from src.configs.config import BASE_DIR
from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR
from src.configs.logger import get_logger
from src.configs.utils import load_latest_task_id
from src.modules.utils import (
    load_file_as_string,
    save_result,
    load_prompt,
    clean_chat_agent_format,
)
from src.schemas.paragraph import Paragraph
from src.modules.heuristic_modules import AbbrReplacer, BibNameReplacer
from src.modules.post_refine import BaseRefiner

logger = get_logger("src.modules.post_refine.RuleBasedRefiner")


class RuleBasedRefiner(BaseRefiner):
    def __init__(self, task_id: str = None, **kwargs) -> None:
        super().__init__(task_id=task_id, **kwargs)
        self.refined_mainbody_path = Path(
            f"{OUTPUT_DIR}/{self.task_id}/tmp/mainbody_rule_refined.tex"
        )

        # 함수
        self.abbr_replacer = AbbrReplacer()
        self.bib_name_replacer = BibNameReplacer(task_id=self.task_id)
        self.sp_phrases_to_be_rm = [
            "Certainly! Below is the rewritten content following your instructions:"
        ]

        # 실행할 치환 규칙
        self.re_pattern_rm_tokens_1 = re.compile(
            pattern=r"\*\*.*?\*\*", flags=re.DOTALL
        )
        self.re_pattern_rm_tokens_2 = re.compile(
            pattern=r"Certainly!.*?following your instructions:", flags=re.DOTALL
        )

        # self.abbr_replacer.process를 사용하면 원인 불명의 중복 버그가 발생해 제외함
        self.replace_rules = [
            # self.abbr_replacer.process,
            self.bib_name_replacer.process,
            self.remove_unexpected_tokens,
        ]

    def rule_replace_pipeline(self, content: str, funcs: list):
        for func in funcs:
            content = func(content=content)
        return content

    def remove_unexpected_tokens(self, content: str):
        for one in self.sp_phrases_to_be_rm:
            content = content.replace(one, "")
        # LLM이 만들어낸 불필요한 표현 제거
        content = re.sub(self.re_pattern_rm_tokens_1, "", content)
        content = re.sub(self.re_pattern_rm_tokens_2, "", content)
        return clean_chat_agent_format(content=content)

    def find_differences(self, str1, str2):
        # 더 짧은 문자열의 길이 구하기
        sents1 = str1.strip().split(".")
        sents2 = str2.strip().split(".")
        # 두 문자열을 비교해 차이를 기록
        differences = []
        for i, (sent_1, sent_2) in enumerate(zip(sents1, sents2)):
            if sent_1 != sent_2:
                differences.append(
                    (
                        i,
                        sent_1.strip().replace("\n\n", ""),
                        sent_2.strip().replace("\n\n", ""),
                    )
                )

        return differences

    def show_differences(
        self, differences, str1_label="revised_content", str2_label="sec_content"
    ):
        for index, sent_1, sent_2 in differences:
            logger.info(
                f"Position {index}: {str1_label} has '{sent_1}'|||||| {str2_label} has '{sent_2}'"
            )

    def run(self, mainbody_path=None, debug=False):
        if mainbody_path is None:
            mainbody_path = self.mainbody_path
        survey_sections = self.load_survey_sections(mainbody_path)
        revised_content_list = []
        for sec in tqdm(survey_sections, desc="Rule based refining..."):
            revised_content = self.rule_replace_pipeline(
                content=sec.content, funcs=self.replace_rules
            )
            if debug:
                differences = self.find_differences(
                    str1=sec.content, str2=revised_content
                )
                self.show_differences(differences=differences)
            revised_content_list.append(revised_content)
        refined_survey_text = "\n".join(revised_content_list)
        save_result(refined_survey_text, self.refined_mainbody_path)
        logger.debug(f"Save content to {self.refined_mainbody_path}.")
        return refined_survey_text


if __name__ == "__main__":
    task_id = load_latest_task_id()
    print(f"task_id: {task_id}")
    # 디버깅 편의를 위해 vector index를 로컬 디렉터리에 저장
    temp_rewriter = RuleBasedRefiner(task_id=task_id, llamaindex_store_local=False)
    mainbody_path = Path(f"{OUTPUT_DIR}/{task_id}/tmp/mainbody_fig_refined.tex")
    temp_rewriter.run(mainbody_path=mainbody_path, debug=True)
