import subprocess
import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent
sys.path.insert(0, str(BASE_DIR))  # 어느 경로에서 실행해도 동작하도록 설정

from src.configs.config import BASE_DIR
from src.configs.logger import get_logger
from src.models.generator import (ContentGenerator, LatexGenerator,
                                  OutlinesGenerator)
from src.models.LLM import ChatAgent
from src.models.post_refine import PostRefiner
from src.modules.preprocessor.preprocessor import single_preprocessing
from src.modules.preprocessor.utils import parse_arguments_for_preprocessor

logger = get_logger("tasks.full_run")

def check_latexmk_installed():
    try:
        # latexmk 명령을 --version 옵션으로 실행해 설치 여부 확인
        _ = subprocess.run(['latexmk', '--version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.debug("latexmk is installed.")
        return True
    except subprocess.CalledProcessError as e:
        logger.debug("latexmk is not installed.")
        return False
    except FileNotFoundError:
        logger.debug("latexmk is not installed.")
        return False

def generate_single_survey(task_id: str, chat_agent: ChatAgent=None):
    if chat_agent is None:
        chat_agent = ChatAgent()

    # outline 생성
    outline_generator = OutlinesGenerator(task_id)
    outline_generator.run()

    # survey 본문 생성
    content_generator = ContentGenerator(task_id=task_id)
    content_generator.run()

    # 사후 정제(post refine)
    post_refiner = PostRefiner(task_id=task_id, chat_agent=chat_agent)
    post_refiner.run()

    # 전체 survey 생성
    latex_generator = LatexGenerator(task_id=task_id)
    latex_generator.generate_full_survey()

    # LaTeX 컴파일
    if check_latexmk_installed():
        logger.info(f"Start compiling with latexmk.")
        latex_generator.compile_single_survey()
    else:
        logger.error(f"Compiling failed, as there is no latexmk installed in this machine.")


if __name__ == "__main__":
    args = parse_arguments_for_preprocessor()
    task_id = single_preprocessing(args)
    generate_single_survey(task_id=task_id)
