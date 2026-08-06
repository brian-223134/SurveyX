import logging
import sys
from typing import Optional
from pathlib import Path

from src.configs.config import BASE_DIR


class ColorFormatter(logging.Formatter):
    """컬러 로그 포매터"""

    COLOR_CODES = {
        logging.ERROR: "\033[91m",  # 빨강
        logging.WARNING: "\033[93m",  # 노랑
        logging.INFO: "\033[92m",  # 초록
        logging.DEBUG: "\033[37m",  # 회색
    }
    RESET_CODE = "\033[0m"

    def format(self, record):
        color = self.COLOR_CODES.get(record.levelno, "")
        message = super().format(record)
        return f"{color}{message}{self.RESET_CODE}"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG)

    # 컬러 포맷을 적용한 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = ColorFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)

    # 기본 포맷을 사용하는 파일 핸들러
    output_dir = Path(f"{BASE_DIR}/outputs/logs")
    output_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(output_dir / f"{name}.log", "a")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


if __name__ == "__main__":
    # 사용 예시
    logger = get_logger("my_logger")
    logger.debug("This is a debug message.")
    logger.info("This is an info message.")
