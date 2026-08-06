# 오프라인 실행 (전체 파이프라인)
python tasks/offline_run.py --title "Controllable Text Generation for Large Language Models: A Survey" --key_words "controlled text generation, text generation, large language model, LLM" --ref_path "dir/path/to/your/references-markdowns"


# 워크플로우 (단계별 실행, 디버깅 전용)
python tasks/workflow/02_clean_data.py --title "Controllable Text Generation for Large Language Models: A Survey" --key_words "controlled text generation, text generation, large language model, LLM" --ref_path "../refs"
task_id="xxx" # task_id는 이전 명령이 만든 outputs/<task_id>/tmp_config.json 에서 확인할 수 있습니다
python tasks/workflow/03_gen_outlines.py  --task_id $task_id
python tasks/workflow/04_gen_content.py  --task_id $task_id
python tasks/workflow/05_post_refine.py  --task_id $task_id
python tasks/workflow/06_gen_latex.py  --task_id $task_id
