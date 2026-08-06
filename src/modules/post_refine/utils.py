from typing import List
import re


def are_key_words_contained(content: str, key_words: List[str] = []):
    for one in key_words:
        if one.strip().lower() in content.strip().lower():
            return True
    return False


def list_citation_names(content: str):
    # \cite{...}, \citet{...}, \citep{...} 같은 패턴을 찾는 정규표현식
    pattern = r"\\cite[t|p]?{([^}]+)}"
    # 패턴에 해당하는 모든 항목 찾기
    citations = re.findall(pattern, content)
    return citations
