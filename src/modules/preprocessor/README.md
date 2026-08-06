# src.modules.preprocessor

## 파일 구조
```
├── data_cleaner.py
├── data_fetcher.py
├── paper_recaller.py
├── README.md
└── utils.py
```

### data_cleaner.py
`DataCleaner` 클래스의 구현체.

주요 기능:
- **JSON 디렉터리에서 논문 로드 (`from_json_dir`)**: JSON 파일이 들어 있는 디렉터리에서 논문을 불러온다. md_text 필드가 있는 논문만 포함한다.
- **누락된 제목 보완 (`complete_title`)**: md_text의 첫 줄에서 제목을 추출해 누락된 제목을 채운다.
- **누락된 초록 보완 (`complete_abstract`)**: md_text에서 "abstract" 구간을 찾아 최대 2000자를 초록으로 추출한다. 별도의 "abstract" 구간을 찾지 못하면 md_text의 앞 2000자를 사용한다.
- **BibTeX 정보 보완 (`complete_bib`)**: 논문에 대한 BibTeX 항목을 생성하고 bib_name을 할당한다.
- **논문 유형 분류 (`get_paper_type`)**: ChatAgent를 사용해 초록을 바탕으로 논문을 사전 정의된 범주(method, benchmark, theory, survey 등)로 분류한다.
- **Attribute Tree 추출 (`get_attri`)**: ChatAgent를 사용해 각 논문의 유형(method, benchmark 등)에 맞춰 md_text에서 attribute tree를 추출한다.
- **정제된 논문 저장 (`save_papers`)**: title, abstract, BibTeX 이름, 논문 유형, 속성 등의 필드를 포함한 정제 결과를 개별 JSON 파일로 저장한다.
- **전체 정제 파이프라인 실행 (`run`)**: 위의 모든 기능을 포함한 전체 정제 과정을 실행한다.


### data_fetcher.py
`DataFetcher` 클래스의 구현체.

주요 기능:
- **인증 관리 (`_get_db_authentication`)**: 데이터베이스 접근을 위한 인증 과정을 관리한다.
- **웹 크롤링 작업 제출 (`task_submit`)**: 큐 기반 시스템(예: Google Scholar 검색)에 작업을 제출하고, 추적용 고유 search_id를 반환한다.
- **작업 진행 상황 추적 (`task_track`)**: 일정 간격으로 큐 상태를 조회해 제출한 작업의 진행 상황을 모니터링한다. 큐에 남아 있는 활성 메시지(작업) 수를 추적한다.
- **데이터베이스에서 데이터 조회 (`_get_data`)**: 지정한 filter와 projection을 사용해 데이터베이스 컬렉션(예: Google Scholar 또는 arXiv 논문)에서 데이터를 가져온다.
- **Google Scholar 검색 (`search_on_google`)**: Google Scholar에 검색 작업을 제출하고 진행 상황을 추적한 뒤, 작업이 완료되면 데이터베이스에서 결과를 가져온다.
- **arXiv 검색 (`search_on_arxiv`)**: 지정한 키워드가 제목이나 초록에 등장하는 논문을 arXiv 데이터베이스에서 가져온다.


### paper_recaller.py
`PaperRecaller` 클래스의 구현체.

주요 기능:
- **반복적 논문 리콜 (`recall_papers_iterative`)**: 진화하는 키워드를 기반으로 여러 번의 반복을 거쳐 논문을 리콜한다. 각 반복은 논문 검색, 임베딩, 클러스터링, 새 키워드 생성으로 구성된다.
- **논문 검색 (`_search_papers`)**: 지정한 키워드로 arXiv와 Google Scholar에서 논문을 검색한다.
- **논문 풀 정리 (`_clean_paper_pool`)**: 제목과 초록을 확인해 유효하지 않거나 중복된 논문을 풀에서 제거한다.
- **논문 임베딩 (`_embed_papers`)**: EmbedAgent를 사용해 제목과 초록을 기반으로 논문 임베딩을 생성한다. 임베딩에 실패한 논문은 풀에서 제거한다.
- **논문 클러스터링 (`_cluster_papers`)**: KMeans 알고리즘으로 임베딩을 기준으로 논문을 클러스터링한다.
- **키워드 생성 (`_generate_keywords`)**: ChatAgent를 사용해 논문 클러스터로부터 다음 리콜 반복에 사용할 새 키워드를 생성한다.
- **새 키워드 선택 (`_select_new_keyword`)**: 생성된 키워드들의 임베딩을 기존 키워드들과 코사인 거리로 비교해 가장 적절한 키워드를 선택한다.


### PaperFilter.py

`PaperFilter` 클래스는 사용자가 정의한 topic과의 관련성을 기준으로 논문 집합을 필터링하고 정렬하기 위한 클래스다.

주요 기능:
- **저장된 디렉터리에서 논문 로드 (`from_saved`)**: 지정한 디렉터리에 JSON 형식으로 저장된 논문을 불러와 `PaperFilter` 클래스를 초기화한다. JSON 파일만 처리하며, 불러온 논문 수를 로그로 남긴다.
- **Coarse-Grained 정렬 (`coarse_grained_sort`)**: 사용자 topic과 의미적으로 가장 관련 있는 상위 K개의 논문을 선택하는 거친 단위의 필터를 적용한다. 벡터 유사도를 기반으로 논문을 빠르고 넓게 걸러내기 위한 단계다.
- **Fine-Grained 정렬 (`fine_grained_sort`)**: 보다 정밀한 선별을 위해 `ChatAgent`로 LLM을 호출해 각 논문의 초록을 topic과 대조해 심층 분석한다. 모델 응답을 기준으로 관련성이 높다고 판단된 논문만 남긴다.
- **필터 실행 (`run`)**: coarse-grained 정렬과 fine-grained 정렬을 결합해 지정한 topic과 가장 관련 있는 최종 논문 목록을 만든다. 먼저 coarse 정렬로 후보를 좁힌 뒤 fine-grained 필터링으로 정제한다.

# Surveyx - 전처리(Preprocess)
이 단계는 두 개의 절차로 구성된다.
1. arXiv와 Google Scholar에서 논문을 가져온다.
2. 논문 데이터를 정제하고 보완한다.

## arXiv와 Google Scholar에서 논문 가져오기
이 단계는 recall과 filter 두 국면으로 나뉜다.

**recall** 국면.
먼저 사용자가 입력한 키워드를 초기 `key_word pool`로 삼는다.
```python
while len(recalled_papers) < 300 and iter_times < 5:
    recalled_papers += recall_paper_from_arxiv_and_googlescholar(key_word_pool)
    kinds = cluster_papers_by_embedding(recalled_papers, num_kinds=len(key_word_pool)+1) # len(keyword_pool)+1 개의 군집으로 클러스터링
    new_keyword = generate_new_key_word_to_each_kind(kinds)
    selected_new_keyword = select_new_keyword_using_cosine_distance(new_keyword, key_word_pool)
    key_word_pool += selected_new_keyword
```

**filter** 국면.
1. coarse-grained 정렬: 초록과 topic 사이의 유사도로 논문을 정렬한다.
2. fine-grained 정렬: LLM에 질의해 논문을 필터링한다.
