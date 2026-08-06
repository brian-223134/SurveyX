import json
from pathlib import Path
import re

from src.configs.logger import get_logger
from src.modules.utils import load_file_as_string, save_result
import os

logger = get_logger("Outlines")


class SingleOutline:
    def __init__(self, title: str, desc: str, sub: list = []) -> None:
        """단일 outline을 생성한다.

        Args:
            title (str): 이 outline의 제목
            desc (str): 설명. 이 outline에 무엇을 쓸지에 해당한다
            sub (list): 하위 subsection들을 가리킨다
        """
        self.title: str = title
        self.desc: str = desc
        self.sub: list[SingleOutline] = sub

    @staticmethod
    def construct_secondary_outline_from_dict(dic: dict) -> None:
        """2차(subsection) outline을 생성한다.

        Args:
            dic (dict): "subsection title"과 "description" 키를 가진 딕셔너리
        """
        return SingleOutline(dic["subsection title"], dic["description"])

    @staticmethod
    def construct_primary_outline_from_dict(dic: dict) -> None:
        """여러 2차 outline을 포함하는 1차(section) outline을 생성한다.

        Args:
            dic (dict): "section title", "description", "subsections" 키를 가진 딕셔너리
        """
        dic.setdefault("subsections", [])
        sub = [
            SingleOutline.construct_secondary_outline_from_dict(x)
            for x in dic["subsections"]
        ]
        return SingleOutline(dic["section title"], dic["description"], sub)

    def __str__(self):
        return "\n".join([self.title, self.desc])


class Outlines:
    """survey의 outline 구조."""

    def __init__(self, title: str, sections: list[SingleOutline]) -> None:
        """Outlines를 생성한다."""
        self.title: str = title
        self.sections: list[SingleOutline] = sections

    @staticmethod
    def from_saved(file_path: str) -> "Outlines":
        """저장된 JSON 파일에서 불러온다. 항상 "title"과 "sections" 키를 가진 딕셔너리다."""
        dic = json.loads(load_file_as_string(file_path))
        title = dic["title"]
        sections = []
        for sec in dic["sections"]:
            sections.append(SingleOutline.construct_primary_outline_from_dict(sec))
        logger.debug("construct outlines from saved path: {}".format(file_path))
        return Outlines(title, sections)

    @staticmethod
    def from_dict(dic: dict):
        """딕셔너리로부터 생성한다.

        Args:
            dic (dict): "title"과 "sections" 키를 가진 딕셔너리.

        Returns:
            Outlines
        """
        title = dic["title"]
        sections = []
        for sec in dic["sections"]:
            sections.append(SingleOutline.construct_primary_outline_from_dict(sec))
        return Outlines(title, sections)

    def save_to_file(self, file_path: Path):
        """Outlines 인스턴스를 JSON 파일로 저장한다."""
        dic = self.to_dict()  # Outlines 인스턴스를 딕셔너리로 변환
        save_result(json.dumps(dic, indent=4), file_path)
        logger.debug(f"Outlines saved to {file_path}")

    def to_dict(self) -> dict:
        """딕셔너리 형태로 반환한다."""

        dic = {"title": self.title, "sections": []}
        for section in self.sections:
            dic["sections"].append(
                {
                    "section title": section.title,
                    "description": section.desc,
                    "subsections": [
                        {
                            "subsection title": subsection.title,
                            "description": subsection.desc,
                        }
                        for subsection in section.sub
                    ],
                }
            )
        return dic

    def __str__(self) -> str:
        """Outlines를 문자열로 출력한다.

        Returns:
            str: 각 section과 subsection 정보를 담은 문자열
        """
        res = [self.title]
        for i, sec in enumerate(self.sections):
            res.append(f"{i + 1}. " + sec.__str__())
            for j, subsec in enumerate(sec.sub):
                res.append(f"{i + 1}.{j + 1} " + subsec.__str__())
        return "\n".join(res)

    def serial_no_to_single_outline(self, serial_no_raw: str) -> SingleOutline | None:
        """survey 내 일련번호를 대응하는 single outline으로 매핑한다.
        예를 들어 "1.1"을 주면 "1.1 xxx, xxxx"에 해당하는 outline을 반환한다.

        Args:
            serial_no (str): "1.1", "2.1", "5" 같은 형태

        Returns:
            SingleOutline: 대응하는 single outline.
        """
        try:
            if "." in serial_no_raw:
                serial_no = re.search(r"\d+\.\d*", serial_no_raw).group(0)
                primary_section_index = int(serial_no.split(".")[0])
                secondary_section_index = serial_no.split(".")[1]
                if secondary_section_index != "":
                    secondary_section_index = int(secondary_section_index)
                    return self.sections[primary_section_index - 1].sub[
                        secondary_section_index - 1
                    ]
                else:
                    return self.sections[primary_section_index - 1]
            else:
                serial_no = re.search(r"\d+", serial_no_raw).group(0)
                primary_section_index = int(serial_no)
                return self.sections[primary_section_index - 1]
        except Exception as e:
            logger.error(
                f"Error occurs: {e}, the serial_no_raw is {serial_no_raw}, the serial_no is {serial_no}"
            )


def unitest():
    p = os.path.join("outputs", "2025-01-10-1935_recom", "outlines.json")
    outlines = Outlines.from_saved(p)
    # print(outlines)
    print(outlines.serial_no_to_single_outline("3"))


# python -m src.schemas.outlines
if __name__ == "__main__":
    unitest()
