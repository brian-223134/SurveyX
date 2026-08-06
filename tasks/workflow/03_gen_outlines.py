import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))  # 어느 경로에서 실행해도 동작하도록 설정

from src.models.generator import OutlinesGenerator
from src.modules.preprocessor.utils import parse_arguments_for_integration_test

# python tasks/integration_test/gen_outlines.py --task_id 2024-11-30-0022_atten
if __name__ == "__main__":
    task_id = parse_arguments_for_integration_test()

    og = OutlinesGenerator(task_id)
    og.run()













