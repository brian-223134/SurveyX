import io
import os
import subprocess
import sys
import traceback
from pathlib import Path

import fitz

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))  # 어느 경로에서 실행해도 동작하도록 설정

from src.configs.constants import OUTPUT_DIR, RESOURCE_DIR
from src.configs.logger import get_logger
from src.configs.utils import load_latest_task_id
from src.models.LLM import ChatAgent
from src.models.monitor.time_monitor import TimeMonitor
from src.modules.latex_handler.latex_text_builder import LatexTextBuilder

logger = get_logger("src.modules.generator.LatexGenerator")


class LatexGenerator:
    def __init__(self, task_id: str, **kwargs):
        task_id = load_latest_task_id() if task_id is None else task_id
        assert task_id is not None
        self.task_id = task_id
        self.outlines_path = Path(f"{OUTPUT_DIR}/{str(self.task_id)}/outlines.json")

        # text builder용 설정
        self.init_text_tex_path = Path(f"{RESOURCE_DIR}/latex/survey.ini.tex")
        self.mainbody_tex_path = Path(
            f"{OUTPUT_DIR}/{str(self.task_id)}/tmp/mainbody_post_refined.tex"
        )
        self.post_refined_mainbody_tex_path = Path(
            f"{OUTPUT_DIR}/{str(self.task_id)}/tmp/mainbody_post_refined.tex"
        )
        self.abstract_path = Path(f"{OUTPUT_DIR}/{str(self.task_id)}/tmp/abstract.tex")
        self.survey_tex_path = Path(
            f"{OUTPUT_DIR}/{str(self.task_id)}/latex/survey.tex"
        )

        # builder 초기화
        # -- 텍스트
        self.text_builder = LatexTextBuilder(init_tex_path=self.init_text_tex_path)

    def add_watermark(self, input_pdf: Path, output_pdf: Path, watermark_pdf: Path):
        # 입력 PDF와 워터마크 PDF 열기
        doc = fitz.open(input_pdf)
        watermark = fitz.open(watermark_pdf)
        # 워터마크 페이지 가져오기(워터마크 파일은 1페이지로 가정)
        watermark_page = watermark[0]
        # 워터마크 페이지의 pixmap(이미지) 가져오기
        watermark_pixmap = watermark_page.get_pixmap()
        # 워터마크 이미지를 바이트 스트림으로 변환
        img_stream = io.BytesIO(watermark_pixmap.tobytes())
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # 현재 페이지 크기 가져오기
            page_rect = page.rect
            # 워터마크 이미지를 페이지에 삽입
            page.insert_image(page_rect, stream=img_stream, overlay=False, alpha=0.3)
        # 수정된 PDF 저장
        doc.save(output_pdf)

    def compile_single_survey(self):
        time_monitor = TimeMonitor(self.task_id)
        time_monitor.start("compile latex")

        task_dir = Path(BASE_DIR) / "outputs" / self.task_id
        latex_dir = task_dir / "latex"
        sty_file_path = Path(BASE_DIR) / "resources" / "latex" / "neurips_2024.sty"
        water_mark_pdf_path = Path(BASE_DIR) / "resources" / "latex" / "watermark.png"

        os.chdir(task_dir)
        if task_dir.joinpath("survey.pdf").exists():
            # output/survey.pdf 파일 삭제
            subprocess.run(f"rm survey.pdf", shell=True)
            subprocess.run(f"rm survey_wtmk.pdf", shell=True)

        # latex 디렉터리로 이동
        os.chdir(latex_dir)

        # sty 파일 준비
        subprocess.run(["cp", sty_file_path, "./neurips_2024.sty"])

        # latexmk 명령 실행. 출력은 compile.log로 리다이렉트
        with open("compile.log", "w") as output_file:
            logger.debug(
                f'Running "latexmk -pdf -interaction=nonstopmode -f survey.tex". The compile.log is at {latex_dir / "compile.log"}'
            )
            subprocess.run(
                "latexmk -pdf -interaction=nonstopmode -f survey.tex",
                shell=True,
                stdout=output_file,
                stderr=output_file,
            )

        # latexmk -c 를 실행해 중간 파일 삭제
        with open("compile.log", "a") as output_file:
            logger.debug(f'Running "latexmk -c"')
            subprocess.run("latexmk -c", shell=True, stdout=output_file)

        # 모든 .bbl 파일 삭제
        subprocess.run("rm *.bbl", shell=True)

        subprocess.run("rm neurips_2024.sty", shell=True)

        # 생성된 survey.pdf를 상위 디렉터리로 이동
        subprocess.run("mv survey.pdf ../", shell=True)
        self.add_watermark(
            task_dir / "survey.pdf", task_dir / "survey_wtmk.pdf", water_mark_pdf_path
        )

        time_monitor.end("compile latex")

    def generate_full_survey(self):
        # survey.tex 생성
        tex_content = self.text_builder.run(
            outlines_path=self.outlines_path,
            abstract_path=self.abstract_path,
            main_body_path=self.post_refined_mainbody_tex_path,
            latex_save_path=self.survey_tex_path,
        )
        return tex_content


# python -m src.models.generator.latex_generator
if __name__ == "__main__":
    # task_id = load_latest_task_id()
    task_id = "ref1"
    print(f"task_id: {task_id}")
    latex_generator = LatexGenerator(task_id=task_id)

    latex_generator.generate_full_survey()
    latex_generator.compile_single_survey()
