import re
import shutil
import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent
sys.path.insert(0, str(BASE_DIR))  # 어느 경로에서 실행해도 동작하도록 설정

def clean_invalid_task_dirs(outputs_dir="outputs"):
    """
    유효하지 않은 task 디렉터리(survey_wtmk.pdf가 없는 디렉터리)를 정리한다.

    인자:
        outputs_dir: outputs 디렉터리 경로. 기본값은 현재 디렉터리 아래의 outputs
    """
    outputs_path = Path(outputs_dir)
    if not outputs_path.exists():
        print(f"Warning: {outputs_path} directory not exists")
        return

    # task 디렉터리명 매칭 패턴 정의(YYYY-MM-DD-HHMM 형식으로 시작)
    task_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}-\d{4}_.+')
    
    deleted_dirs = []
    kept_dirs = []

    for task_dir in outputs_path.iterdir():
        if not task_dir.is_dir():
            continue
            
        # 디렉터리명 형식 검증
        if not task_pattern.match(task_dir.name):
            continue

        # 대상 파일 존재 여부 확인
        target_file = task_dir / "survey_wtmk.pdf"
        if not target_file.exists():
            try:
                shutil.rmtree(task_dir)
                deleted_dirs.append(task_dir.name)
            except Exception as e:
                print(f"Failed to delete {task_dir}: {str(e)}")
        else:
            kept_dirs.append(task_dir.name)

    # 정리 결과 출력
    print(f"Deleted directories ({len(deleted_dirs)}):")
    for d in sorted(deleted_dirs):
        print(f" - {d}")
    
    print(f"\nKept directories ({len(kept_dirs)}):")
    for d in sorted(kept_dirs):
        print(f" - {d}")

if __name__ == "__main__":
    clean_invalid_task_dirs(BASE_DIR / "outputs")