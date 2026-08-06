import os
import re
from pathlib import Path
from typing import List

from tenacity import retry, stop_after_attempt, wait_fixed
from tqdm import tqdm

from src.configs.config import ADVANCED_CHATAGENT_MODEL, BASE_DIR
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent
from src.modules.latex_handler.latex_base_table_builder import LatexBaseTableBuilder
from src.modules.utils import (
    load_file_as_string,
    load_meta_data,
    load_prompt,
    load_single_file,
    save_as_json,
    save_result,
)

logger = get_logger("src.modules.latex_handler.LatexSummaryTableBuilder")


class LatexSummaryTableBuilder(LatexBaseTableBuilder):
    def __init__(
        self,
        main_body_path: Path,
        tmp_path: Path,
        latex_path: Path,
        paper_dir: Path,
        outline_path: Path,
        prompt_dir: Path,
        chat_agent: ChatAgent,
    ):
        self.chat_agent = chat_agent
        super().__init__(chat_agent=self.chat_agent)
        self.main_body_path = main_body_path
        self.outline_path = outline_path
        self.method_table_tex_path = latex_path / "summary_table.tex"
        self.paper_dir = paper_dir
        self.extract_prompt_path = prompt_dir / "Extract_Prompt.txt"
        self.summary_prompt_path = prompt_dir / "Attribute_Summary.txt"
        self.tmp_path = tmp_path
        self.description_prompt_path = prompt_dir / "Table_description.txt"
        self.rewrite_prompt_path = prompt_dir / "Content_rewrite.txt"
        # self.exist_primary_attribute_path = os.path.join(tmp_path, "exist/Primary Attribute.json")
        self.exist_attribute_path = tmp_path / "exist/Attribute.json"

    def find_method_section(self) -> str:
        outlines = load_single_file(self.outline_path)
        section_titles, subsection_titles = self.parse_outline(outlines)
        ans = None  # 조건을 만족하는 원소를 저장
        for section_title in section_titles:
            if (
                "method" in section_title.lower()
                or "technique" in section_title.lower()
            ):
                ans = section_title
                break  # 조건을 만족하므로 루프 종료
        if ans == None:
            prompt = load_prompt(
                f"{BASE_DIR}/resources/LLM/prompts/latex_table_builder/find_method_section.md",
                outline=str(outlines),
            )
            res = self.chat_agent.remote_chat(
                text_content=prompt, model=ADVANCED_CHATAGENT_MODEL
            )
            if res is None:
                return None
            try:
                ans = re.search(r"<Answer>(.*?)</Answer>", res, re.DOTALL)
                if ans:
                    ans = ans.group(1)
                else:
                    print("Error: No <Answer> tag found in the input text.")
                    return
            except Exception as e:
                return
        title = ans
        logger.debug(f"Select method section '{title}' to generate summary_table.")
        return title

    def generate_method_table(self, section_name: str):
        """
        표를 생성하는 메인 함수.
        """
        order = 0
        section_content = self.extract_section_content(
            self.main_body_path, section_name
        )
        section_mainbody = self.extract_section_mainbody(
            self.main_body_path, section_name
        )
        if section_content is None:
            return
        subsections, titles = self.extract_subsections(section_content)
        dict_list = []
        for subsection, pri_attribute in tqdm(
            zip(subsections, titles), total=len(subsections)
        ):
            order += 1
            cite_names = self.extract_cite_name(subsection)
            meta_data = load_meta_data(self.paper_dir)
            for name in cite_names:
                complete_info, content, title, method_name, abbr, bib_name = (
                    self.cite_name_match(meta_data, name)
                )
                if content is not None and title is not None:
                    result = self.process_paper(
                        subsection,
                        content,
                        title,
                        method_name,
                        abbr,
                        bib_name,
                        pri_attribute,
                        order,
                    )
                    dict_list.append(result)
            if len(dict_list) == 0:
                continue
            process_dict_list = self.process_data(dict_list)
            prompt = load_prompt(
                self.summary_prompt_path,
                Input=process_dict_list,
            )
            result = self.chat_agent.remote_chat(
                text_content=prompt, model=ADVANCED_CHATAGENT_MODEL
            )
            map_dict = self.extract_and_convert(result)
            if map_dict is None:
                return
            final_dict_list = self.replace_secondary_attributes(dict_list, map_dict)
            for dict in final_dict_list:
                title = dict["title"]
                filename = f"{title}.json"
                path = os.path.join(self.tmp_path, filename)
                save_as_json(result=dict, path=path)
            dict_list = []
            self.clear_json_file(self.exist_attribute_path)

        self.generate_method_table_file(section_content, section_mainbody)

    def process_paper(
        self,
        context: str,
        content: str,
        title: str,
        method_name: str,
        abbr: str,
        bib_name: str,
        pri_attribute: str,
        order: int,
    ):
        """
        Args:
            context: 표로 요약해야 하는 section에 대응하는 문맥.
            content: 논문에서 소개된 method의 내용.
            title: 논문 파일 이름.
            method_name: 논문에서 소개된 method 이름.
            abbr: method의 약어.
            bib_name: 논문의 bib_name.
        """

        exist_attribute = load_single_file(self.exist_attribute_path)
        attributes = "previously extracted Attributes: \n" + str(exist_attribute)

        prompt = load_prompt(
            self.extract_prompt_path,
            Content=content,
            Context=context,
            Domain=pri_attribute,
            Attributes=attributes,
        )
        result = self.chat_agent.remote_chat(
            text_content=prompt, model=ADVANCED_CHATAGENT_MODEL
        )
        result = self.extract_attributes(result, pri_attribute)
        if result is None:
            return
        self.process_article(result, self.exist_attribute_path)

        result["title"] = title
        result["method name"] = method_name
        result["abbr"] = abbr
        result["bib_name"] = bib_name
        result["cite_name"] = abbr.replace("&", "\\&") + f"\\cite{{{bib_name}}}"
        result["order"] = order
        # filename = f"{title}.json"  # Specify the output file extension
        return result

    def generate_method_table_latex(self, data):
        """
        데이터를 기반으로 표의 LaTeX 코드를 생성한다.
        """
        latex_code = "\\begin{table}[htbp]\n\\centering\n\\resizebox{\\textwidth}{!}{ %\n\\begin{tabular}{p{0.65\\textwidth} p{0.47\\textwidth} p{0.5\\textwidth}}\n\\toprule\n"
        latex_code += "\\texfbf{Category} & \\texfbf{Feature} & \\texfbf{Method} \\\\\n\\midrule\n"
        # 각 카테고리 순회
        for idx, (category, features, methods) in enumerate(
            zip(data["Category"], data["Feature"], data["Method"])
        ):
            row_span = len(features)  # 해당 카테고리에 필요한 행 병합 수 계산

            # 카테고리와 feature를 굵게 표시
            category_bold = f"\\textbf{{{category}}}"  # 카테고리를 굵게 표시
            features_bold = [f"{feature}" for feature in features]  # feature를 굵게 표시

            # 행 병합과 가운데 정렬을 적용해 카테고리 추가
            if row_span > 1:
                latex_code += f"\\multirow{{{row_span}}}{{*}}{{\\centering {category_bold}}} & {features_bold[0]} & {', '.join(methods[0])} \\\\\n"
            else:
                latex_code += f"{category_bold} & {features_bold[0]} & {', '.join(methods[0])} \\\\\n"

            # 카테고리를 제외한 나머지 feature/method 행 추가
            for i in range(1, len(features)):
                latex_code += f"& {features_bold[i]} & {', '.join(methods[i])} \\\\\n"

            # 카테고리 사이에 가로선 추가(마지막 카테고리 뒤는 제외)
            if idx < len(data["Category"]) - 1:
                latex_code += "\\midrule\n"

        latex_code += "\\bottomrule\n\\end{tabular}\n}\n\\caption{Methods Summary}\n\\label{tab:summary_table}\n\\end{table}"

        return latex_code

    def generate_method_table_file(self, section_content, section_mainbody):
        """
        데이터를 사용해 표의 LaTeX 파일을 생성한다.
        """
        if section_mainbody == "":
            return
        table_data = self.load_table_data(self.tmp_path)
        if table_data is None:
            return
        convert_data = self.data_convert(table_data)
        latex_code = self.generate_method_table_latex(convert_data)
        caption, introductory_sentence = self.generate_description(
            latex_code, section_content
        )
        if caption is not None:
            caption = re.sub(r"\{[^}]*\}", "", caption)
            caption = re.sub(r"\\[a-zA-Z]+(\{[^}]*\})?", "", caption)
        if caption is not None and introductory_sentence is not None:
            try:
                latex_code = re.sub(
                    r"\\caption\{.*?\}", rf"\\caption{{{caption}}}", latex_code
                )
            except re.error as e:
                print(f"Error during regex substitution for latex_code: {e}")
                return
            try:
                introductory_sentence = re.sub(
                    r"\\?input\{.*?\}",
                    rf"\\ref{{tab:summary_table}}",
                    introductory_sentence,
                )
            except re.error as e:
                print(f"Error during regex substitution for introductory_sentence: {e}")
                return
            tex = load_file_as_string(self.main_body_path)
            prompt = load_prompt(
                self.rewrite_prompt_path,
                Content=section_mainbody,
                Sentence=introductory_sentence,
            )
            res = self.chat_agent.remote_chat(
                text_content=prompt, model=ADVANCED_CHATAGENT_MODEL
            )
            # 도입 문장 추가
            try:
                revised_content = re.search(r"<Answer>(.*?)</Answer>", res, re.DOTALL)
                if revised_content:
                    revised_content = revised_content.group(1)
                else:
                    print("Error: No <Answer> tag found in the input text.")
                    return
            except Exception as e:
                return
            tex = tex.replace(section_mainbody, revised_content)
            save_result(tex, self.main_body_path)
            # input\{summary_table} 추가
            tex = load_file_as_string(self.main_body_path)
            section_title = self.extract_section_title(section_content)
            tex = tex.replace(
                section_title, f"{section_title}\n\n\\input{{summary_table}}"
            )
            save_result(tex, self.main_body_path)
            self.save_table_file(latex_code, self.method_table_tex_path)
            logger.info(f"Summary LaTeX table saved to {self.method_table_tex_path}")

    @staticmethod
    def get_sections(survey_path: str) -> List[str]:
        """
        survey의 section 이름들을 가져온다.
        """
        tex = open(survey_path, "r").read()
        pattern = r"\\section{"
        match_l = list(re.finditer(pattern, tex))
        res = []
        for i in range(len(match_l) - 1):
            section_tex = tex[match_l[i].start() : match_l[i + 1].start()]
            res.append(section_tex)
        return res

    @staticmethod
    def get_title(section: str) -> str:
        """
        section의 제목을 가져온다.
        """
        title = re.findall(r"\\section\{([^}]+)\}", section)[0]
        return title

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    def run(self):
        method_section = self.find_method_section()
        self.generate_method_table(method_section)
