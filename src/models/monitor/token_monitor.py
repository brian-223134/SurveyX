import json
import threading
from pathlib import Path
from typing import Dict

import yaml

from src.configs.constants import BASE_DIR, OUTPUT_DIR
from src.configs.logger import get_logger
from src.schemas.base import Base

logger = get_logger("src.modules.monitor.token_monitor")


class TokenMonitor(Base):
    def __init__(self, task_id: str, label: str):
        super().__init__(task_id)

        # LLM 가격 정보 파일 로드
        self._config_path = BASE_DIR / "src" / "configs" / "LLM.yaml"
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"LLM pricing file doesn't exist: {self._config_path}"
            )
        else:
            self.pricing = self._load_pricing_config()

        self.record_file: Path = OUTPUT_DIR / task_id / "metrics" / "token_monitor.json"
        self.record_file.parent.mkdir(parents=True, exist_ok=True)

        self.record: Dict[str, Dict[str, list]] = {}
        self.label: str = label

        # 스레드 락 추가
        self._lock = threading.Lock()

    def _load_pricing_config(self) -> Dict:
        try:
            with open(self._config_path, "r") as f:
                config = yaml.safe_load(f)
            return config
        except (yaml.YAMLError, KeyError) as e:
            logger.error(f"가격 설정 로드 실패: {str(e)}")
            raise
        except Exception as e:
            logger.critical(f"설정 파일을 읽을 수 없음: {str(e)}")
            raise

    def add_token(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        label: str | None = None,
    ) -> float:
        with self._lock:  # 락 획득
            if model not in self.pricing:
                logger.debug(f"{model} 의 가격 정보가 설정되지 않음")
                input_price = self.pricing["default"]["input"]
                output_price = self.pricing["default"]["output"]
            else:
                input_price = self.pricing[model]["input"]
                output_price = self.pricing[model]["output"]

            # 이번 호출 비용 계산(소수점 4자리 유지)
            cost = round(
                (input_tokens / 1000000 * float(input_price))
                + (output_tokens / 1000000 * float(output_price)),
                12,
            )
            # 라벨 기록 구조 초기화
            if label == None:
                label = self.label
            if label not in self.record:
                self.record[label] = {}
            # model 키로 기록 직접 조회
            if model not in self.record[label]:
                self.record[label][model] = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_cost": cost,
                }
            else:
                # 기존 기록 값에 누적
                self.record[label][model]["input_tokens"] += input_tokens
                self.record[label][model]["output_tokens"] += output_tokens
                self.record[label][model]["total_cost"] = round(
                    self.record[label][model]["total_cost"] + cost, 12
                )
            # 기록 저장
            self._save_record(label)
        return cost

    def _save_record(self, label: str) -> None:
        """
        이 함수 자체에는 스레드 락이 없다. add token 함수 쪽에 락이 걸려 있으므로,
        이 함수를 호출하는 모든 곳에서 반드시 락을 걸어야 한다.
        """
        try:
            # 기존 기록 읽기
            existing = {}
            if self.record_file.exists():
                with open(self.record_file, "r") as f:
                    existing = json.load(f)

            # 현재 라벨의 기록만 갱신(다른 라벨 데이터는 유지)
            existing[label] = self.record[label]

            # 원자적 쓰기
            with open(self.record_file, "w") as f:
                json.dump(existing, f, indent=4)

        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"token 기록 저장 실패: {str(e)}")
            raise


def stress_test(monitor: TokenMonitor):
    for _ in range(1000):
        monitor.add_token("gpt-4o", 100, 50, "stress_test")


# python -m src.models.monitor.token_monitor
if __name__ == "__main__":
    # 사용 예시
    monitor = TokenMonitor("test", "test_label")

    # 첫 번째 호출
    cost1 = monitor.add_token("gpt-4o", 1500, 800)
    print(f"이번 비용: ${cost1}")

    # 두 번째 호출
    cost2 = monitor.add_token("gpt-4o", 2000, 1200)
    print(f"이번 비용: ${cost2}")

    cost3 = monitor.add_token("gpt-4o-mini", 2000, 1200)
    print(f"이번 비용: ${cost3}")

    cost4 = monitor.add_token("qwen", 2000, 1200)
    print(f"이번 비용: ${cost4}")

    # 누적 기록 확인
    print("현재 기록:", monitor.record)

    # 멀티스레드 테스트
    threads = [threading.Thread(target=stress_test, args=(monitor,)) for _ in range(10)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 결과 검증
    record = monitor.record["stress_test"]["gpt-4o"]
    assert record["input_tokens"] == 100 * 1000 * 10  # 스레드당 100회 × 10스레드
    assert record["output_tokens"] == 50 * 1000 * 10
