import os
import json
import re
import ast
from collections import defaultdict
from typing import List, Tuple
from itertools import combinations
from difflib import SequenceMatcher
from src.configs.logger import get_logger
from src.configs.config import ADVANCED_CHATAGENT_MODEL
from src.modules.utils import (
    load_meta_data,
    load_prompt,
)
from src.configs.config import BASE_DIR
from src.models.LLM import ChatAgent

logger = get_logger("src.modules.latex_handler.BaseTableBuilder")


class LatexBaseTableBuilder:
    def __init__(self, chat_agent: ChatAgent = None):
        """
        기반 클래스 초기화 메서드. 하위 클래스가 자체 초기화 로직을 구현할 수 있도록
        의도적으로 비워 두었다.
        """
        self.chat_agent = chat_agent if chat_agent is not None else ChatAgent()

    def clear_json_file(self, file_path):
        # 파일을 열어 내용을 비움
        with open(file_path, "w") as f:
            # 빈 딕셔너리를 기록해 내용을 초기화
            json.dump([], f)

    def is_the_row_good(self, row: str, splitter: str = "&"):
        elements = row.strip().split(splitter)
        unexpected_element_count = 0
        for one in elements:
            if one.strip() in ["-", ""]:
                unexpected_element_count += 1
        if unexpected_element_count >= 2:
            return False
        return True

    def cite_name_match(self, data_list: List, cite_name: str) -> Tuple:
        """
        cite name을 기준으로 attribute tree에서 관련 정보를 가져온다.

        Args:
            data_list: attribute tree를 담고 있는 리스트.
            cite_name: 논문의 cite name.

        Returns:
            tuple: attribute tree 내 method 설명 정보를 담은 튜플.
        """
        for data in data_list:
            if (
                data["bib_name"] == cite_name
                and data["paper_type"] == "method"
                and data["attri"] is not None
                and len(data["attri"]["method"]["method abbreviation"].split()) < 2
            ):
                content = (
                    "method name:"
                    + data["attri"]["method"]["method name"]
                    + "\n"
                    + "method_step: \n "
                    + str(data["attri"]["method"]["method steps"])
                )
                complete_info = str(data["attri"])
                return (
                    complete_info,
                    content,
                    data["title"],
                    data["attri"]["method"]["method name"],
                    data["attri"]["method"]["method abbreviation"],
                    data["bib_name"],
                )
        return None, None, None, None, None, None

    def cite_name_match_count(self, data_list, cite_names):
        count = 0
        for cite_name in cite_names:
            if any(
                data["bib_name"] == cite_name and data["paper_type"] == "method"
                for data in data_list
            ):
                count += 1
        return count

    def cite_name_match_benchmark(self, data_list: List, cite_name):
        info = {}
        for data in data_list:
            if (
                data["bib_name"] == cite_name
                and data["paper_type"] == "benchmark"
                and data["attri"] is not None
                and len(data["attri"]["idea"]["benchmark abbreviation"].split()) < 2
                and self.convert_to_number(data["attri"]["dataset"]["size"]) is not None
                and self.convert_to_number(data["attri"]["dataset"]["size"]) < 10000000
            ):
                info["size"] = data["attri"]["dataset"]["size"]
                info["domain"] = data["attri"]["dataset"]["domain"]
                info["task format"] = data["attri"]["dataset"]["task format"]
                info["metric"] = data["attri"]["metrics"]["metric name"]
                info["bib_name"] = data["bib_name"]
                info["name"] = data["attri"]["idea"]["benchmark abbreviation"]
                # info = (
                # "Background: " + str(data['attri']['background']) + "\n" +
                # "Dataset information: " + str(data['attri']['dataset']) + "\n" +
                # "Metric information: " + str(data['attri']['metrics'])
                # )
                return info
        return None

    def extract_attributes(self, file_content, pri_attribute):
        """
        LLM 응답에서 필요한 정보를 추출한다.

        Args:
            file_content: LLM의 응답.

        Returns:
            tuple: 속성 이름과 그 설명을 담은 튜플.
        """
        # 새로운 정규표현식으로 변경
        primary_pattern = re.compile(
            r"\[Attribute:\s*(.*?)\]", re.DOTALL
        )  # "Attribute: Name" 매칭
        description_pattern = re.compile(
            r"\[Description:\s*(.*?)\]", re.DOTALL
        )  # "Description: XXX" 매칭

        # 매칭된 내용 추출
        primary_match = primary_pattern.search(file_content)
        description_match = description_pattern.search(file_content)

        # 결과 초기화
        attribute_name = None
        description_text = None

        # Primary Attribute를 찾으면 그 내용을 추출
        if primary_match:
            attribute_name = primary_match.group(1)

        # Description을 찾으면 그 내용을 추출
        if description_match:
            description_text = description_match.group(1)

        if attribute_name is None or description_text is None:
            return None
        # 결과 딕셔너리
        result = {
            "Primary Attribute Name": pri_attribute,
            "Secondary Attribute Name": attribute_name,
            "Description": description_text,
        }
        return result

    def save_attributes(self, attribute_name, description, file_name, type):
        """
        속성들을 지정한 JSON 파일에 저장한다.
        """
        directory = os.path.dirname(file_name)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        if not os.path.exists(file_name):
            data = []
        else:
            with open(file_name, "r") as file:
                data = json.load(file)
        if type == 0:
            new_entry = {
                "Primary Attribute Name": attribute_name,
                "Description": description,
            }
            # 동일한 Primary Attribute Name이 이미 있는지 확인
            exists = any(
                item.get("Primary Attribute Name") == attribute_name for item in data
            )
        elif type == 1:
            new_entry = {
                "Secondary Attribute Name": attribute_name,
                "Description": description,
            }
            # 동일한 Primary Attribute Name이 이미 있는지 확인
            exists = any(
                item.get("Secondary Attribute Name") == attribute_name for item in data
            )
        # 없으면 리스트에 추가하고 파일에 기록
        if not exists:
            data.append(new_entry)
            with open(file_name, "w") as file:
                json.dump(data, file, indent=4)

    # 논문에서 소개된 method 처리
    def process_article(self, result, secondary_attribute_path):
        """
        결과에서 속성 데이터를 불러온다.
        """
        # # Primary Attribute Name 처리
        # primary_attribute = result.get("Primary Attribute Name")
        # primary_description = result.get("Description1")
        # if primary_attribute and primary_description:
        #     save_attributes(primary_attribute, primary_description, primary_attribute_path, 0)

        # Secondary Attribute Name 처리
        secondary_attribute = result.get("Secondary Attribute Name")
        secondary_description = result.get("Description")
        if secondary_attribute and secondary_description:
            self.save_attributes(
                secondary_attribute, secondary_description, secondary_attribute_path, 1
            )

    def process_data(self, data_list):
        """
        딕셔너리 리스트를 처리해 특정 속성을 추출하고 원하는 형식으로 정리한다.
        이때 Secondary Attribute Name의 중복은 제거한다.
        """
        result = {}
        secondary_attributes = []
        seen_names = set()  # 이미 처리한 'Secondary Attribute Name'을 추적하는 집합

        for item in data_list:
            if item is None:
                continue
            primary_attr = item.get("Primary Attribute Name")
            secondary_attr_name = item.get("Secondary Attribute Name")
            description = item.get("Description")

            # Secondary Attribute Name이 중복이면 건너뜀
            if secondary_attr_name in seen_names:
                continue

            # 중복이 아닌 Secondary Attribute Name을 집합에 추가
            seen_names.add(secondary_attr_name)

            # 해당 secondary attribute를 리스트에 추가
            secondary_attributes.append(
                {"Name": secondary_attr_name, "Description": description}
            )

            # 결과 딕셔너리에 Primary Attribute 설정(모든 Primary Attribute Name이 동일하다고 가정)
            if "Primary Attribute" not in result:
                result["Primary Attribute"] = primary_attr

        # Secondary Attribute 리스트를 결과 딕셔너리에 할당
        result["Secondary Attributes"] = secondary_attributes

        return result

    def replace_secondary_attributes(self, data_list, attribute_dict):
        """
        data_list의 'Secondary Attribute Name'이 attribute_dict의 값에 존재하면,
        해당 항목을 attribute_dict의 키로 치환한다.

        Parameters:
            data_list (list): 'Secondary Attribute Name'을 담은 딕셔너리 리스트.
            attribute_dict (dict): 카테고리와 속성 이름을 매핑한 딕셔너리.

        Returns:
            list: 'Secondary Attribute Name'이 치환된 리스트.
        """
        # 속성 → 카테고리 역매핑 생성
        reverse_mapping = {
            attr: key for key, attrs in attribute_dict.items() for attr in attrs
        }

        # 리스트의 각 딕셔너리 처리
        for item in data_list:
            secondary_name = item.get("Secondary Attribute Name")
            if secondary_name in reverse_mapping:
                # secondary attribute 이름을 카테고리로 치환
                item["Secondary Attribute Name"] = reverse_mapping[secondary_name]

        return data_list

    def extract_and_convert(self, text):
        # 정규표현식으로 <Answer> 태그 안의 내용 추출
        match = re.search(r"<Answer>\s*(\{.*?\})\s*</Answer>", text, re.DOTALL)
        if match:
            content = match.group(1)
            try:
                # ast.literal_eval로 문자열을 안전하게 Python 딕셔너리로 파싱
                dictionary = ast.literal_eval(content)
                return dictionary
            except (SyntaxError, ValueError) as e:
                print(f"Error parsing content: {e}")
                return None
        else:
            print("No valid content found in <Answer> tags.")
            return None

    def data_convert(self, triplets):
        """
        원본 데이터를 원하는 형식으로 변환한다.
        """
        # 딕셔너리 초기화
        data = defaultdict(lambda: defaultdict(list))

        # 삼중항(triplet) 데이터 순회
        for triplet in triplets:
            category = triplet["Category"]
            feature = triplet["Feature"]
            method = triplet["Method"]
            # 해당 feature 아래에 method 추가
            data[category][feature].append(method)

        # defaultdict를 목표 데이터 형식으로 변환
        final_data = {"Category": [], "Feature": [], "Method": []}

        # 최종 딕셔너리 구성
        for category, features in data.items():
            final_data["Category"].append(category)
            feature_list = []
            method_list = []
            for feature, methods in features.items():
                feature_list.append(feature)
                method_list.append(methods)
            final_data["Feature"].append(feature_list)
            final_data["Method"].append(method_list)
        return final_data

    def extract_cite_name(self, text: str) -> List[str]:
        """
        문단에서 cite name을 추출한다.
        """
        # 정규표현식으로 \cite{xxx} 안의 내용을 매칭
        result = []
        cite_names = re.findall(r"\\cite\{(.*?)\}", text)
        for name in cite_names:
            if name not in result:
                result.append(name)
        return result

    def load_table_data(self, dir_path):
        """
        표 생성에 필요한 원본 파일들을 불러온다.
        """
        data = []
        # 각 파일의 읽기 결과를 임시 저장
        temp_data = []

        # 디렉터리 내 파일 순회
        if not os.path.isdir(dir_path):
            print(f"The directory {dir_path} does not exist or is not accessible.")
            return None
        for filename in os.listdir(dir_path):
            if filename.endswith(".json"):
                file_path = os.path.join(dir_path, filename)
                with open(file_path, "r", encoding="utf-8") as file:
                    result = json.load(file)  # JSON 파일 내용을 Python 딕셔너리로 읽기
                    # 데이터를 읽어 순서대로 추가
                    dict = {}
                    dict["Category"] = result["Primary Attribute Name"]
                    dict["Feature"] = result["Secondary Attribute Name"]
                    dict["Method"] = result["cite_name"]
                    dict["Order"] = result["order"]  # 순서 값 가져오기
                    temp_data.append(dict)

        # 'Order' 기준으로 데이터 정렬
        temp_data.sort(key=lambda x: x["Order"])  # 'Order' 필드 기준 정렬

        # 정렬된 데이터를 최종 결과 리스트에 추가
        for item in temp_data:
            data.append(
                {
                    "Category": item["Category"],
                    "Feature": item["Feature"],
                    "Method": item["Method"],
                }
            )

        return data

    def extract_section_content(self, tex_file_path: str, section_name: str) -> str:
        """
        .tex 파일에서 특정 section의 내용을 추출한다.

        Args:
            tex_file_path (str): 읽어들일 .tex 파일 경로.
            section_name (str): 추출할 section 이름.

        Returns:
            str: 해당 section의 내용.
        """
        with open(tex_file_path, "r", encoding="utf-8") as file:
            content = file.read()
        # 정규표현식으로 지정한 section과 그 내용을 매칭
        pattern = re.compile(
            r"(\\section\{" + re.escape(section_name) + r"\}.*?)(?=\\section|$)",
            re.DOTALL,
        )
        match = pattern.search(content)
        if match:
            return match.group(1).strip()
        else:
            return None
            # return f"Section '{section_name}' not found."

    def extract_section_mainbody(self, tex_file_path: str, section_name: str) -> str:
        """
        .tex 파일에서 특정 section의 내용을 추출한다. section 제목과 label은 제외한다.

        Args:
            tex_file_path (str): 읽어들일 .tex 파일 경로.
            section_name (str): 추출할 section 이름.

        Returns:
            str: 해당 section의 내용.
        """
        with open(tex_file_path, "r", encoding="utf-8") as file:
            content = file.read()

        # 정규표현식으로 지정한 section 본문을 매칭. \section과 \label 부분은 제외
        pattern = re.compile(
            r"\\section\{"
            + re.escape(section_name)
            + r"\}(?:\s*\\label\{.*?\})?\s*(.*?)(?=\\subsection|\\section|$)",
            re.DOTALL,
        )

        match = pattern.search(content)
        if match:
            return match.group(1).strip()
        else:
            return None

    def extract_subsection_content(
        self, tex_file_path: str, subsection_name: str
    ) -> str:
        """
        .tex 파일에서 특정 subsection의 내용을 추출한다.

        Args:
            tex_file_path (str): 읽어들일 .tex 파일 경로.
            section_name (str): 추출할 subsection 이름.

        Returns:
            str: 해당 subsection의 내용.
        """
        with open(tex_file_path, "r", encoding="utf-8") as file:
            content = file.read()
        # 정규표현식으로 지정한 subsection과 그 내용을 매칭
        pattern = re.compile(
            rf"(\\subsection\{{{re.escape(subsection_name)}\}}.*?)(?=(\\section|\\subsection|$))",
            re.DOTALL,
        )
        match = pattern.search(content)
        if match:
            return match.group(1).strip()
        else:
            return None
            # return f"subsection '{subsection_name}' not found."

    def extract_subsections(self, text):
        # 정규표현식으로 각 subsection 제목과 그 내용을 매칭
        # subsection과 그 내용 매칭
        subsection_pattern = r"(\\subsection\{.*?\}.*?)(?=\\subsection|$)"
        subsections = re.findall(subsection_pattern, text, re.DOTALL)

        title_pattern = r"\\subsection\{(.*?)\}"
        titles = [re.search(title_pattern, sub).group(1) for sub in subsections]
        # subsection 제목과 내용 반환
        return [sub.strip() for sub in subsections], [title for title in titles]

    def extract_section_title(self, text):
        # 정규표현식으로 \section 으로 시작하는 문단 추출
        section_pattern = r"\\section\{.*?\}.*?\\label\{.*?\}"
        section_title = re.findall(section_pattern, text, re.DOTALL)
        return section_title[0]

    def extract_subsection_title(self, text):
        # 정규표현식으로 \section 으로 시작하는 문단 추출
        section_pattern = r"\\subsection\{.*?\}.*?\\label\{.*?\}"
        section_title = re.findall(section_pattern, text, re.DOTALL)
        return section_title[0]

    def supplement_data(self, current_data, dir_path, target_size):
        """
        데이터 개수가 target_size에 도달하도록 리콜 데이터를 보충한다.
        :param current_data: 현재 리콜된 데이터 리스트(딕셔너리 타입)
        :param dir_path: 데이터베이스 폴더 경로
        :param target_size: 목표 데이터 개수
        :return: 최종 데이터 리스트
        """
        # 폴더에서 모든 데이터 읽기
        data_list = load_meta_data(dir_path)
        benchmark_list = []
        for data in data_list:
            if data["paper_type"] == "benchmark":
                benchmark_list.append(data)
        # 현재 리콜된 데이터의 bib_name 필드 집합 추출
        current_bib_names = {item["bib_name"] for item in current_data}

        # 데이터베이스에서 기존 데이터와 중복되는 항목을 제외하고 지정한 필드만 추출
        remaining_data = []
        for item in benchmark_list:
            if (
                item["bib_name"] not in current_bib_names
                and item["attri"] is not None
                and len(item["attri"]["idea"]["benchmark abbreviation"].split()) < 2
                and self.convert_to_number(item["attri"]["dataset"]["size"]) is not None
                and self.convert_to_number(item["attri"]["dataset"]["size"]) < 10000000
            ):
                info = {
                    "name": item["attri"]["idea"]["benchmark abbreviation"],
                    "size": item["attri"]["dataset"]["size"],
                    "domain": item["attri"]["dataset"]["domain"],
                    "task format": item["attri"]["dataset"]["task format"],
                    "metric": item["attri"]["metrics"]["metric name"],
                    "bib_name": item["bib_name"],
                }
                remaining_data.append(info)

        # 데이터 보충
        supplemented_data = current_data[:]
        for item in remaining_data:
            if len(supplemented_data) < target_size:
                supplemented_data.append(item)
            else:
                break

        return supplemented_data

    def get_sections(self, survey_path: str) -> List[str]:
        """
        survey의 section 이름들을 가져온다.

        Args:
            survey_path (str): survey TeX 파일 경로.

        Returns:
            List[str]: section 내용 문자열 리스트.
        """
        tex = open(survey_path, "r").read()
        pattern = r"\\section{"
        match_l = list(re.finditer(pattern, tex))
        res = []
        for i in range(len(match_l) - 1):
            section_tex = tex[match_l[i].start() : match_l[i + 1].start()]
            res.append(section_tex)
        return res

    def save_table_file(self, latex_code, output_file):
        # LaTeX 코드를 .tex 파일로 저장
        with open(output_file, "w") as file:
            file.write(latex_code)

    def generate_description(self, latex_code, content):
        prompt = load_prompt(
            f"{BASE_DIR}/resources/LLM/prompts/latex_table_builder/Table_description.txt",
            Latex=latex_code,
            Content=content,
        )
        result = self.chat_agent.remote_chat(
            text_content=prompt, model=ADVANCED_CHATAGENT_MODEL
        )
        result = self.extract_and_convert(result)
        if result is not None:
            caption = result.get("caption")  # 'caption'이 없으면 None 반환
            introductory_sentence = result.get(
                "introductory sentence"
            )  # 'introductory sentence'가 없으면 None 반환
            return caption, introductory_sentence
        return None, None

    def get_value_list(self, data):
        list1 = [list(d.values())[1] for d in data]
        list2 = [list(d.values())[2] for d in data]
        list3 = [list(d.values())[3] for d in data]
        return [list1, list2, list3]

    def validity_judge(self, data):
        count = 0
        for element in data:
            if "-" in element:
                count += 1

        # 리스트 길이의 절반을 넘는지 판단
        if count > len(data) / 2:
            return 0
        return 1

    def format_string(self, s):
        if not s:  # 빈 문자열이거나 None이면 그대로 반환
            return s
        words = s.split(" ")
        formatted_words = []
        for word in words:
            if len(word) == 2:  # 단어가 두 글자로만 이루어져 있으면 전부 대문자로 변환
                formatted_word = word.upper()
            elif "-" in word:  # 하이픈이 포함된 단어 처리
                parts = word.split("-")
                formatted_word = "-".join([parts[0].capitalize()] + parts[1:])
            else:
                formatted_word = word.capitalize()
            formatted_words.append(formatted_word)
        return " ".join(formatted_words)

    def calculate_similarity(self, list_of_strings, threshold=0.7):
        """
        문자열 리스트의 유사도 지표를 계산한다. 이상치는 건너뛴다.

        Args:
            list_of_strings (list): 각 원소가 문자열인 리스트.
            threshold (float): 유사도 임계값. 이 값보다 크면 높은 유사도로 간주한다.

        Returns:
            int: 유사도가 높은 문자열 쌍의 개수.
            float: 유사도 지표(정규화 값).
        """

        def preprocess(s):
            """문자열 전처리: 단어를 정렬하고 소문자로 변환한다"""
            return " ".join(sorted(s.lower().split()))

        def similarity(s1, s2):
            """두 문자열의 유사도를 계산한다(SequenceMatcher 기반)"""
            return SequenceMatcher(None, s1, s2).ratio()

        def is_valid(s):
            """문자열이 유효한 값인지 판단한다(이상치 제외)"""
            # 이상치 정의: 문장부호로만 이루어졌거나 비어 있는 경우
            return bool(s.strip()) and not re.fullmatch(r"[-_.]+", s.strip())

        # 유효하지 않은 문자열 필터링(이상치 건너뜀)
        filtered_strings = [s for s in list_of_strings if is_valid(s)]

        # 문자열 전처리
        processed_strings = [preprocess(s) for s in filtered_strings]

        # 두 개씩 조합해 유사도 계산
        high_similarity_pairs = 0
        total_pairs = 0
        for s1, s2 in combinations(processed_strings, 2):
            total_pairs += 1
            if similarity(s1, s2) >= threshold:
                high_similarity_pairs += 1

        # 유사도 지표
        similarity_score = high_similarity_pairs / total_pairs if total_pairs > 0 else 0
        return similarity_score

    def convert_to_number(self, number_str):
        """
        "10000000" 또는 "1,000,000" 같은 숫자 문자열을 정수로 변환한다.

        Args:
            number_str (str): 숫자의 문자열 표현.

        Returns:
            int: 변환된 정수 값.
        """
        try:
            # 문자열에서 쉼표 제거
            cleaned_str = number_str.replace(",", "")
            # 정리된 문자열을 정수로 변환
            return int(cleaned_str)
        except ValueError:
            return None

    def parse_outline(self, data):
        # 두 개의 리스트 초기화
        section_titles = []
        subsection_titles = []

        # section들을 순회하며 제목 추출
        for section in data["sections"]:
            # section title 추출
            if "section title" in section:
                section_titles.append(section["section title"])

            # subsection title 추출
            if "subsections" in section:
                for subsection in section["subsections"]:
                    if "subsection title" in subsection:
                        subsection_titles.append(subsection["subsection title"])
        return section_titles, subsection_titles

    def get_sections(self, survey_path: str) -> List[str]:
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

    def get_title(self, section: str) -> str:
        """
        section의 제목을 가져온다.
        """
        title = re.findall(r"\\section\{([^}]+)\}", section)[0]
        return title
