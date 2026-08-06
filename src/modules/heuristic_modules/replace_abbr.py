import re


class AbbrReplacer(object):
    def __init__(self):
        self._abbr_dict = {}  # 전체 표현과 약어 쌍을 저장
        self.first_occurrences = set()  # 최초 등장 시 예외 처리가 필요한 전체 표현 기록
        # 정규표현식으로 전체 표현과 약어를 매칭
        # 약어의 글자 수와 전체 표현의 단어 수가 일치하는지 확인하는 로직 추가
        self.pattern = re.compile(r"\s+\(([A-Z]+)\)")
        self.punc_pattern = re.compile(r"[,.]\s*|\n")

    def find_abbr_pairs(self, content: str):
        segs = re.split(self.punc_pattern, content)
        for one in segs:
            one = one.strip()
            if one == "":
                continue
            matches = re.finditer(self.pattern, one)
            for match in matches:
                abbr = match.group(1)
                pos = match.start()  # 약어의 시작 위치

                # abbr은 한 단어여야 한다
                if len(abbr.strip().split()) > 1:
                    continue
                words_num = len(abbr)

                # 전체 표현의 단어 수 계산
                words = one[:pos].strip().split()[-words_num:]

                full_name = " ".join(words)

                # 약어가 각 단어의 첫 글자와 일치하는지 추가 확인
                if all(
                    word[0].upper() == abbr_char for word, abbr_char in zip(words, abbr)
                ):
                    if full_name not in self._abbr_dict:
                        self._abbr_dict[full_name] = abbr
                        self.first_occurrences.add(full_name)  # 최초 등장 집합에 추가
        return self._abbr_dict

    # 전체 표현을 약어로 치환 (최초 등장은 예외)
    def replace_full_name_with_abbr(self, match):
        # 전체 표현 부분만 사용해 매칭
        full_name_only = match.group(1)
        if full_name_only in self.first_occurrences:
            # 최초 등장이면 집합에서 제거하고 치환은 건너뜀
            self.first_occurrences.remove(full_name_only)
            return match.group(0)  # 수정하지 않은 전체 매칭 내용 반환
        # 약어로 치환
        return self._abbr_dict[full_name_only]

    def process(self, content: str):
        # 새로운 약어 쌍을 먼저 수집
        self.find_abbr_pairs(content)

        # 텍스트 처리: 전체 표현 및 "전체 표현(약어)" 형태를 치환
        for full_name, abbr in self._abbr_dict.items():
            full_name_pattern = (
                r"\b(" + re.escape(full_name) + r")(\s+\(" + re.escape(abbr) + r"\))?"
            )
            content = re.sub(
                full_name_pattern, self.replace_full_name_with_abbr, content
            )

        return content


# 사용 예시
if __name__ == "__main__":
    replacer = AbbrReplacer()
    text = """Natural Language Processing (NLP) is a branch of artificial intelligence (AI).
              This course on Natural Language Processing (NLP) will cover several topics in artificial intelligence .
              Natural Language Processing  is a branch of artificial intelligence .
              This course on Natural Language Processing (NLP) will cover several topics in artificial intelligence ."""
    processed_text = replacer.process(text)
    print(processed_text)
