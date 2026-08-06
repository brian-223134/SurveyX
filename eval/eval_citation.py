import json
import os
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from tenacity import retry, stop_after_attempt, wait_fixed
from tqdm import tqdm

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent

from utils import load_file_as_string, remote_chat

TOPICS = """In-context Learning
Out-of-Distribution Detection
Semi-Supervised Learning
LLMs for Recommendation
LLM-Generated Texts Detection
Explainability for LLMs
Evaluation of LLMs
LLMs-based Agents
LLMs in Medicine
Domain Specialization of LLMs
Challenges of LLMs in Education
Alignment of LLMs
ChatGPT
Instruction Tuning for LLMs
LLMs for Information Retrieval
Safety in LLMs
Chain of Thought
Hallucination in LLMs
Bias and Fairness in LLMs
Large Multi-Modal Language Models
Acceleration for LLMs
LLMs for Software Engineering
""".splitlines()

svx_path = Path(f"{BASE_DIR}/data/svx")
# print(remote_chat("hello"))


@retry(stop=stop_after_attempt(5), wait=wait_fixed(1))
def nli(claim: str, source: str):
    prompt = """---
Claim:
{claim}
---
Source: 
{source}
---
Claim:
{claim}
---
Is the Claim faithful to the Source? 
A Claim is faithful to the Source if the core part in the Claim can be supported by the Source.\n
Only reply with 'Yes' or 'No':""".format(
        claim=claim, source=source
    )
    res = remote_chat(prompt)
    if "no" in res.lower():
        return False
    else:
        return True


def get_refs(paper_dir: Path) -> dict:
    bibname2abs = defaultdict(str)
    for file in os.listdir(paper_dir):
        p = paper_dir / file
        with open(p, "r") as f:
            paper_dict = json.load(f)
        key = paper_dict["bib_name"]
        value = paper_dict["md_text"]
        bibname2abs[key] = value
    return bibname2abs


def extract_cite_and_text(text: str) -> list[list[str], str]:
    cites = re.findall(r"\\cite\{([^}]+)\}", text)
    cite_list = []
    for cite in cites:
        for single_cite in cite.split(","):
            cite_list.append(single_cite.strip())
    cleaned_text = re.sub(r"\\cite\{[^}]+\}", "", text)

    return cite_list, cleaned_text.strip()


def parse_a_paper(paper_path: Path, bibname2abs: dict) -> dict:
    content = load_file_as_string(paper_path)
    claim2source = {}
    sentences = re.split(r"[.\n]+", content)
    for sentence in sentences:
        if r"\cite{" in sentence:
            sources, claim = extract_cite_and_text(sentence)
            abss = [bibname2abs[source] for source in sources]
            claim2source[claim] = abss
    return claim2source


if __name__ == "__main__":
    # 논문별로 claim과 source 수집
    res_per_paper = []
    for topic in tqdm(TOPICS):
        ref_dir = Path(f"{BASE_DIR}/data/ref/{topic}")
        mainbody_path = Path(f"{BASE_DIR}/data/svx/{topic}.tex")
        bibname2abs = get_refs(ref_dir)

        claim2source = parse_a_paper(mainbody_path, bibname2abs)

        claim_TF = {}
        for claim, sources in claim2source.items():
            source_TF = []
            for source in sources:
                source_TF.append(nli(claim, source))
            claim_TF[claim] = source_TF
        res_per_paper.append([claim2source, claim_TF, mainbody_path])

    # recall과 precision 계산
    recall_l = []
    precision_l = []
    for claim2source, claim_TF, path in res_per_paper:
        supported_claim = 0
        claim_num = len(claim2source)
        claim_source_pair_num = 0
        claim_source_pair_supported_num = 0

        for claim in claim2source.keys():
            source = claim2source[claim]
            tf = claim_TF[claim]
            t_count = tf.count(True)

            if t_count > 0:
                supported_claim += 1
            claim_source_pair_num += len(tf)
            if t_count == 0:
                claim_source_pair_supported_num += len(tf)
            else:
                claim_source_pair_supported_num += t_count

        eval_dict = {
            "claim_num": claim_num,
            "supported_claim": supported_claim,
            "source_num": claim_source_pair_num,
            "supported_source_num": claim_source_pair_supported_num,
        }

        recall = eval_dict["supported_claim"] / eval_dict["claim_num"]
        precision = eval_dict["supported_source_num"] / eval_dict["source_num"]
        recall_l.append(recall)
        precision_l.append(precision)
    print("recall: ", np.mean(recall_l))
    print("precision: ", np.mean(precision_l))
