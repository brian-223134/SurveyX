import json
import pandas as pd
from pathlib import Path
from collections import defaultdict

def collect_metrics_data(outputs_dir="outputs"):
    """조건에 맞는 모든 task의 지표 데이터를 수집한다"""
    outputs_path = Path(outputs_dir)
    token_data = defaultdict(lambda: defaultdict(list))  # 구조: {stage: {model: [metrics]}}
    time_data = defaultdict(list)                        # 구조: {stage: [durations]}
    
    # outputs 디렉터리 순회
    for task_dir in outputs_path.iterdir():
        if not task_dir.is_dir():
            continue
        
        # 필수 파일 존재 여부 확인
        if not (task_dir / "survey_wtmk.pdf").exists():
            continue
        if not (task_dir / "metrics").exists():
            continue
            
        # token 모니터링 데이터 처리
        token_file = task_dir / "metrics" / "token_monitor.json"
        if token_file.exists():
            with open(token_file) as f:
                try:
                    data = json.load(f)
                    for stage, models in data.items():
                        for model, metrics in models.items():
                            token_data[stage][model].append({
                                "input_tokens": metrics["input_tokens"],
                                "output_tokens": metrics["output_tokens"],
                                "total_cost": metrics["total_cost"]
                            })
                except Exception as e:
                    print(f"Error reading {token_file}: {str(e)}")
        
        # 시간 모니터링 데이터 처리
        time_file = task_dir / "metrics" / "time_monitor.json"
        if time_file.exists():
            with open(time_file) as f:
                try:
                    data = json.load(f)
                    for stage, metrics in data.items():
                        if "duration" in metrics:
                            time_data[stage].append(metrics["duration"])
                except Exception as e:
                    print(f"Error reading {time_file}: {str(e)}")
    
    return token_data, time_data

def generate_reports(token_data, time_data):
    """통계 리포트를 생성한다"""
    # Token 통계 리포트
    token_rows = []
    for stage, models in token_data.items():
        for model, metrics_list in models.items():
            avg_input = sum(m["input_tokens"] for m in metrics_list) / len(metrics_list)
            avg_output = sum(m["output_tokens"] for m in metrics_list) / len(metrics_list)
            avg_cost = sum(m["total_cost"] for m in metrics_list) / len(metrics_list)
            
            token_rows.append({
                "단계명": stage,
                "모델명": model,
                "평균 입력 token": round(avg_input, 2),
                "평균 출력 token": round(avg_output, 2),
                "평균 비용": round(avg_cost, 6)
            })
    
    # Time 통계 리포트
    time_rows = []
    for stage, durations in time_data.items():
        if durations:
            avg_duration = sum(durations) / 60 / len(durations)
            time_rows.append({
                "단계명": stage,
                "평균 소요 시간(분)": round(avg_duration, 2),
                "샘플 수": len(durations)
            })
    
    return pd.DataFrame(token_rows), pd.DataFrame(time_rows)

def save_to_excel(token_df, time_df):
    """Excel 파일로 저장한다"""
    with pd.ExcelWriter("metrics_summary.xlsx") as writer:
        # 데이터 기록
        token_df.to_excel(writer, sheet_name="Token 통계", index=False)
        time_df.to_excel(writer, sheet_name="소요 시간 통계", index=False)
        
        # 워크시트 객체 가져오기
        token_sheet = writer.sheets["Token 통계"]
        time_sheet = writer.sheets["소요 시간 통계"]
        
        # Token 통계 열 너비 설정
        for idx, col_name in enumerate(token_df.columns):
            max_len = max(
                token_df[col_name].astype(str).str.len().max(),  # 데이터 최대 길이
                len(str(col_name))  # 열 제목 길이
            ) + 2
            token_sheet.set_column(idx, idx, max_len)
        
        # 소요 시간 통계 열 너비 설정
        for idx, col_name in enumerate(time_df.columns):
            max_len = max(
                time_df[col_name].astype(str).str.len().max(),
                len(str(col_name))
            ) + 2
            time_sheet.set_column(idx, idx, max_len)

if __name__ == "__main__":
    token_data, time_data = collect_metrics_data()
    token_df, time_df = generate_reports(token_data, time_data)
    save_to_excel(token_df, time_df)
    print(f"리포트 생성 완료: {Path('metrics_summary.xlsx').resolve()}")