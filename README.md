<h2 align="center">SurveyX: 대규모 언어 모델을 활용한 학술 서베이 자동 생성</h2>

<p align="center">
  <i>
✨SurveyX에 오신 것을 환영합니다! 전체 기능을 사용해 보시려면 저희 웹사이트에 로그인해 주세요. 이 오픈소스 코드는 오프라인 처리 기능만 제공합니다.✨
  </i>
  <br>
  <a href="https://arxiv.org/abs/2502.14776">
      <img src="https://img.shields.io/badge/arXiv-Paper-red.svg?logo=arxiv" alt="arxiv paper">
  </a>
  <a href="http://www.surveyx.cn">
    <img src="https://img.shields.io/badge/SurveyX-Web-blue?style=flat" alt="surveyx.cn">
  </a>
  <a href="https://huggingface.co/papers/2502.14776">
    <img src="https://img.shields.io/badge/Huggingface-🤗-yellow?style=flat" alt="huggingface paper">
  </a>
  <a href="https://github.com/IAAR-Shanghai/SurveyX">
    <img src="https://img.shields.io/github/stars/IAAR-Shanghai/SurveyX?style=flat&logo=github&color=yellow" alt="github stars">
  </a>
    <img src="https://img.shields.io/github/last-commit/IAAR-Shanghai/SurveyX?display_timestamp=author&style=flat&color=green" alt="last commit">
  </a>
  <br>
  <a href="https://github.com/IAAR-Shanghai/SurveyX/blob/main/assets/user_groups_123.jpg">
    <img src="https://img.shields.io/badge/Wechat-Group-07c160?style=flat&logo=wechat" alt="Wechat Group">
  </a>
</p>

<div align="center">
    <strong><a>저희 작업이 도움이 되셨다면 스타를 눌러주세요! ⭐️</a></strong>
    <br>
  👉 <strong><a href="https://surveyx.cn/">SurveyX 방문하기</a></strong> 👈
</div>

\[한국어 | [English](README_en.md)\]

## 🤔SurveyX란?

![surveyx_frame](assets/SurveyX.png)

**SurveyX**는 대규모 언어 모델(LLM)의 능력을 활용해 고품질의 도메인 특화 학술 논문 및 서베이를 생성하는 학술 서베이 자동화 시스템입니다. 논문 제목과 문헌 검색용 키워드만 입력하면, 특정 주제에 맞춘 포괄적인 학술 논문이나 서베이를 요청할 수 있습니다.

---

## 🆚 정식 버전 vs. 오프라인 오픈소스 버전

이 저장소의 오픈소스 코드는 오프라인 처리 기능만 제공합니다. 전체 기능을 사용해 보시려면 [저희 웹사이트](https://www.surveyx.cn)에 로그인해 주세요.

**오픈소스 버전에 없는 기능:**
1. **실시간 온라인 검색:** 직접 업로드한 `.md` 형식의 참고문헌만으로 서베이를 생성할 수 있습니다. 오픈소스 버전에는 문헌 수집을 위한 논문 데이터베이스, 웹 크롤러 시스템, 키워드 확장 알고리즘, 2단계 의미 기반 필터링이 포함되어 있지 않습니다.
2. **멀티모달 문서 파싱:** 생성된 서베이에는 참고문헌으로부터의 이미지 이해나 삽화가 포함되지 않습니다.

---

## 🛠️ 오프라인 오픈소스 버전 사용법 (이 저장소)

### 1. 사전 준비

- Python 3.10+ (Anaconda 권장)
- `requirements.txt`에 명시된 모든 Python 의존성
- LaTeX 환경 (PDF 컴파일용)
- 파이프라인을 실행하기 전에, 모든 참고문헌 문서를 Markdown(`.md`) 형식으로 변환해 하나의 폴더에 모아두어야 합니다.

```bash
sudo apt update && sudo apt install texlive-full
```

### 2. 설치

1. 저장소 클론:
```bash
git clone https://github.com/IAAR-Shanghai/SurveyX.git
cd SurveyX
```

2. Python 의존성 설치:
```bash
pip install -r requirements.txt
```

### 3. LLM 설정

파이프라인을 실행하기 전에 `src/configs/config.py`를 수정해 LLM API URL, 토큰, 모델 정보를 입력하세요.

예시:
```python
REMOTE_URL = "https://api.openai.com/v1/chat/completions"
TOKEN = "sk-xxxx..."
DEFAULT_EMBED_ONLINE_MODEL = "BAAI/bge-base-en-v1.5"
EMBED_REMOTE_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_TOKEN = "your embed token here"
```

### 4. 워크플로우

실행할 때마다 `outputs/` 아래에 task id 이름의 고유한 결과 폴더가 생성됩니다(`outputs/<task_id>`, 예: `outputs/2025-06-18-0935_keyword/`).

전체 파이프라인 실행:
```bash
python tasks/offline_run.py --title "Your Survey Title" --key_words "keyword1, keyword2, ..." --ref_path "path/to/your/reference/dir"
```

단계별 실행:
```bash
export task_id="your_task_id"
python tasks/workflow/03_gen_outlines.py --task_id $task_id
python tasks/workflow/04_gen_content.py --task_id $task_id
python tasks/workflow/05_post_refine.py --task_id $task_id
python tasks/workflow/06_gen_latex.py --task_id $task_id
```

**참고:** 로컬 참고문헌 문서는 **반드시 Markdown(`.md`) 형식**이어야 하며, 하나의 디렉터리에 모아두어야 합니다.

### 5. 출력

- 모든 결과는 `outputs/<task_id>/` 아래에 저장됩니다.
  - `survey.pdf`: 최종 컴파일된 서베이
  - `outlines.json`: 생성된 개요(outline)
  - `latex/`: LaTeX 소스
  - `tmp/`: 중간 산출물

---

## 🧭 논문 구현 가이드 (이 포크 전용)

> 이 절은 원본 저장소에는 없는, [SurveyX 논문(arXiv:2502.14776)](https://arxiv.org/abs/2502.14776)을 직접 구현·재현하기 위해 정리한 내용입니다.

**핵심 요약: 논문의 Generation Phase(§3.2)는 이 저장소에 전부 구현되어 있고, Preparation Phase(§3.1)는 알고리즘은 모두 있으나 데이터 소스만 비어 있습니다.** 처음부터 만드는 작업이 아니라 구멍 하나를 메우는 작업입니다.

### 논문 ↔ 코드 매핑

| 논문 | 코드 | 상태 |
|---|---|---|
| §3.1.1 Keyword Expansion (Algorithm 1) | [`paper_recaller.py`](src/modules/preprocessor/paper_recaller.py) `recall_papers_iterative` | ✅ 완전 구현. KMeans `n=|K_pool|+1`, 클러스터별 LLM 키워드 생성, rank 기반 선택, topic 가중치 ×2 |
| §3.1.1 2-step filtration | [`paper_filter.py`](src/modules/preprocessor/paper_filter.py) `coarse_grained_sort` + `fine_grained_sort` | ✅ 완전 구현. 임베딩 Top-K(200) → LLM 관련성 판정 |
| §3.1.1 retrieval data source | [`data_fetcher.py`](src/modules/preprocessor/data_fetcher.py) | ❌ **비어 있음 — 유일한 구멍** |
| §3.1.2 AttributeTree | [`data_cleaner.py`](src/modules/preprocessor/data_cleaner.py) `get_paper_type` + `get_attri`, `resources/LLM/prompts/preprocessor/attri_tree_for_{method,benchmark,theory,survey}.md` | ✅ 완전 구현. 논문 Appendix B의 4개 템플릿 그대로 |
| §3.2.1 Outline Optimization | [`outlines_generator.py`](src/models/generator/outlines_generator.py) `run` | ✅ 5단계(1차 outline → 논문 mount로 hint 생성 → 2차 outline → 중복 제거 → 재구성)가 논문과 일치 |
| §3.2.2 Content Generation | [`content_generator.py`](src/models/generator/content_generator.py) `content_fulfill_iter` | ✅ subsection 단위 생성 + 기생성 본문을 컨텍스트로 전달 |
| §3.2.3 RAG-based Rewriting | [`rag_refiner.py`](src/modules/post_refine/rag_refiner.py) | ✅ |
| §3.2.3 Figure & Table Generation | [`latex_figure_builder.py`](src/modules/latex_handler/latex_figure_builder.py), `latex_*_table_builder.py` | ✅ |
| §3.2.3 MLLM 기반 그림 검색 | [`fig_retrieve_refiner.py`](src/modules/post_refine/fig_retrieve_refiner.py) | ⚠️ `post_refiner.py`에서 호출이 주석 처리됨 + `FIG_RETRIEVE_URL=""` |
| §4.1 content / citation 평가 | [`eval/eval_content.py`](eval/eval_content.py), [`eval/eval_citation.py`](eval/eval_citation.py) | ✅ |
| §4.1 reference relevance (IoU, Relevance_semantic, Relevance_LLM) | — | ❌ 미구현 |

`DataFetcher`가 비어 있는 구체적인 형태: `CRAWLER_BASE_URL = ""`, `_get_db_authentication()`은 `pass`만 있음, `task_submit()`의 `url = f""`, `token: ""`. 사내 크롤러 및 arXiv DB(약 260만 편) 서버에 접속하는 코드가 오픈소스화 과정에서 제거된 것입니다. 그래서 `tasks/offline_run.py`는 `PaperRecaller`/`PaperFilter`를 건너뛰고, 사용자가 제공한 `.md`로 곧바로 `DataCleaner.offline_proc()`을 실행합니다.

### 권장 구현 순서

**0단계 — 환경 문제 해결 (현재 그대로면 실행이 막힙니다)**
- `requirements.txt`의 `fitz==0.0.1.dev2`는 잘못된 패키지입니다. `latex_generator.py`의 `import fitz`는 PyMuPDF를 요구하므로 `PyMuPDF`로 교체해야 합니다.
- `llama-index-embeddings-huggingface`가 `requirements.txt`에 없습니다 (`EmbedAgent`가 `HuggingFaceEmbedding`을 임포트).
- `src/configs/config.py`의 `REMOTE_URL` 기본값이 `https://openai.com/...`인데, 위 설정 예시대로 `https://api.openai.com/...`이 맞습니다.

**1단계 — 오프라인 경로로 end-to-end 먼저 실행**
참고문헌 md 10~20개로 `tasks/offline_run.py`를 실행해 outline → content → post_refine → LaTeX 전 구간이 도는지 확인합니다. 이것만으로 논문 §3.2 전체를 검증하는 셈이고, 프롬프트와 데이터 스키마 감을 잡을 수 있어 이후 작업에 가장 도움이 됩니다.

**2단계 — `DataFetcher` 재구현 (실질적인 "논문 구현" 작업)**
`search_on_arxiv(key_words) -> list[dict]`와 `search_on_google(...) -> list[dict]` 두 메서드의 시그니처만 지키면 상위의 `PaperRecaller`/`PaperFilter`는 수정할 필요가 없습니다. 반환 dict에는 `_id`, `title`, `abstract`, `md_text`(전문), `reference`(BibTeX)가 필요하며, 이 중 `md_text`가 AttributeTree 추출의 입력이므로 전문 확보 여부가 최종 품질을 좌우합니다. 논문의 사내 인프라 대신 arXiv API + Semantic Scholar/OpenAlex 조합이 현실적이며, 전문은 arXiv PDF → Markdown 변환이 필요합니다. `DEFAULT_PAPER_POOL_LIMIT=1024`가 논문의 임계값 θ=1000에 해당합니다.

**3단계 — 평가 지표 보강**
§4.1의 reference relevance 3종(IoU, Relevance_semantic, Relevance_LLM)이 없어 2단계에서 만든 검색 알고리즘의 성능을 측정할 수단이 없습니다. 2단계보다 먼저 갖추는 편이 낫습니다. 논문 Table 2의 ablation은 대부분 설정값으로 재현 가능합니다(`DEFAULT_ITERATION_LIMIT=0`으로 keyword expansion 제거, `get_attri` 결과 대신 `md_text` 직접 투입 등).

**4단계 (선택) — MLLM 기반 그림 검색 복구**
`post_refiner.py`의 주석 처리된 `fig_retrieve_refiner.run(...)` 호출을 되살리고, `FIG_RETRIEVE_URL` 계열 설정을 자체 멀티모달 파이프라인으로 대체합니다.

### 코드를 읽으며 확인한 사항

- `data_fetcher.py`의 `search_on_arxiv`: docstring은 "overlap이 2 이상인 결과를 반환"이라고 하지만 실제 조건은 `id_counter[_id] >= 1`이라 필터가 동작하지 않습니다. 2단계에서 이 함수를 다시 사용할 때 의도대로 고칠지 결정이 필요합니다.
- `paper_recaller.py`의 키워드 선택(`_select_new_keyword`): 논문 본문 산문("평균 거리는 최소, 최대 거리는 최대")과 논문 수식 (1)(2)(3)이 서로 반대인데, **코드는 수식을 따릅니다**(평균 거리가 큰 쪽 + 최대 거리가 작은 쪽 선호). 재구현 시 수식 기준이 맞다고 보면 됩니다.

---

## 예시 논문

| 제목                                                         | 키워드                                                        |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
|[A Survey of NoSQL Database Systems for Flexible and Scalable Data Management](./examples/Database/A_Survey_of_NoSQL_Database_Systems_for_Flexible_and_Scalable_Data_Management.pdf) | NoSQL, Database Systems, Flexibility, Scalability, Data Management |
|[Vector Databases and Their Role in Modern Data Management and Retrieval A Survey](./examples/Database/Vector_Databases_and_Their_Role_in_Modern_Data_Management_and_Retrieval_A_Survey.pdf) | Vector Databases, Data Management, Data Retrieval, Modern Applications |
|[Graph Databases A Survey on Models, Data Modeling, and Applications](./examples/Database/Graph_Databases_A_Survey_on_Models.pdf) | Graph Databases, Data Modeling |
|[A Survey on Large Language Model Integration with Databases for Enhanced Data Management and Survey Analysis](./examples/Database/A_Survey_on_Large_Language_Model_Integration_with_Databases_for_Enhanced_Data_Management_and_Survey_Analysis.pdf) | Large Language Models, Database Integration, Data Management, Survey Analysis, Enhanced Processing |
|[A Survey of Temporal Databases Real-Time Databases and Data Management Systems](./examples/Database/A_Survey_of_Temporal_Databases_Real.pdf) | Temporal Databases, Real-Time Databases, Data Management |
| [From BERT to GPT-4: A Survey of Architectural Innovations in Pre-trained Language Models](./examples/Computation_and_Language/Transformer.pdf) | Transformer, BERT, GPT-3, self-attention, masked language modeling, cross-lingual transfer, model scaling |
| [Unsupervised Cross-Lingual Word Embedding Alignment: Techniques and Applications](./examples/Computation_and_Language/low.pdf) | low-resource NLP, few-shot learning, data augmentation, unsupervised alignment, synthetic corpora, NLLB, zero-shot transfer |
| [Vision-Language Pre-training: Architectures, Benchmarks, and Emerging Trends](./examples/Computation_and_Language/multimodal.pdf) | multimodal learning, CLIP, Whisper, cross-modal retrieval, modality fusion, video-language models, contrastive learning |
| [Efficient NLP at Scale: A Review of Model Compression Techniques](./examples/Computation_and_Language/model.pdf) | model compression, knowledge distillation, pruning, quantization, TinyBERT, edge computing, latency-accuracy tradeoff |
| [Domain-Specific NLP: Adapting Models for Healthcare, Law, and Finance](./examples/Computation_and_Language/domain.pdf) | domain adaptation, BioBERT, legal NLP, clinical text analysis, privacy-preserving NLP, terminology extraction, few-shot domain transfer |
| [Attention Heads of Large Language Models: A Survey](./examples/Computation_and_Language/attn.pdf) | attention head, attention mechanism, large language model, LLM,transformer architecture, neural networks, natural language processing |
| [Controllable Text Generation for Large Language Models: A Survey](./examples/Computation_and_Language/ctg.pdf) | controlled text generation, text generation, large language model, LLM,natural language processing |
| [A survey on evaluation of large language models](./examples/Computation_and_Language/eval.pdf) | evaluation of large language models,large language models assessment, natural language processing, AI model evaluation |
| [Large language models for generative information extraction: a survey](./examples/Computation_and_Language/infor.pdf) | information extraction, large language models, LLM,natural language processing, generative AI, text mining |
| [Internal consistency and self feedback of LLM](./examples/Computation_and_Language/inter.pdf) | Internal consistency, self feedback, large language model, LLM,natural language processing, model evaluation, AI reliability |
| [Review of Multi Agent Offline Reinforcement Learning](./examples/Computation_and_Language/multi-agent.pdf) | multi agent, offline policy, reinforcement learning,decentralized learning, cooperative agents, policy optimization |
| [Reasoning of large language model: A survey](./examples/Computation_and_Language/reason.pdf) | reasoning of large language models, large language models, LLM,natural language processing, AI reasoning, transformer models |
| [Hierarchy Theorems in Computational Complexity: From Time-Space Tradeoffs to Oracle Separations](examples/Computational_Complexity/P_vs_.pdf) | P vs NP, NP-completeness, polynomial hierarchy, space complexity, oracle separation, Cook-Levin theorem |
| [Classical Simulation of Quantum Circuits: Complexity Barriers and Implications](examples/Computational_Complexity/BQP.pdf) | BQP, quantum supremacy, Shor's algorithm, post-quantum cryptography, QMA, hidden subgroup problem |
| [Kernelization: Theory, Techniques, and Limits](examples/Computational_Complexity/fixed.pdf) | fixed-parameter tractable (FPT), kernelization, treewidth, W-hierarchy, ETH (Exponential Time Hypothesis), parameterized reduction |
| [Optimal Inapproximability Thresholds for Combinatorial Optimization Problems](examples/Computational_Complexity/PCP.pdf) | PCP theorem, approximation ratio, Unique Games Conjecture, APX-hardness, gap-preserving reduction, LP relaxation |
| [Hardness in P: When Polynomial Time is Not Enough](examples/Computational_Complexity/SETH.pdf) | SETH (Strong Exponential Time Hypothesis), 3SUM conjecture, all-pairs shortest paths (APSP), orthogonal vectors problem, fine-grained reduction, dynamic lower bounds |
| [Consistency Models in Distributed Databases: From ACID to NewSQL](examples/Database/CAP.pdf) | CAP theorem, ACID vs BASE, Paxos/Raft, Spanner, NewSQL, sharding, linearizability |
| [Cloud-Native Databases: Architectures, Challenges, and Future Directions](examples/Database/CAP.pdf) | cloud databases, AWS Aurora, Snowflake, storage-compute separation, auto-scaling, pay-per-query, multi-tenancy |
| [Graph Database Systems: Storage Engines and Query Optimization Techniques](examples/Database/graph.pdf) | graph traversal, Neo4j, SPARQL, property graph, subgraph matching, RDF triplestore, Gremlin |
| [Real-Time Aggregation in TSDBs: Techniques for High-Cardinality Data](examples/Database/time.pdf) | time-series data, InfluxDB, Prometheus, downsampling, time windowing, high-cardinality indexing, stream processing |
| [Self-Driving Databases: A Survey of AI-Powered Autonomous Management](examples/Database/auto.pdf) | autonomous databases, learned indexes, query optimization, Oracle AutoML, workload forecasting, anomaly detection |
| [Multi-Model Databases: Integrating Relational, Document, and Graph Paradigms](examples/Database/mmd.pdf) | multi-model database, MongoDB, ArangoDB, JSONB, unified query language, schema flexibility, polystore |
| [Vector Databases for AI: Efficient Similarity Search and Retrieval-Augmented Generation](examples/Networking_and_Internet_Architecture/vector.pdf) | vector database, FAISS, Milvus, ANN search, embedding indexing, RAG (Retrieval-Augmented Generation), HNSW |
| [Software-Defined Networking: Evolution, Challenges, and Future Scalability](examples/Networking_and_Internet_Architecture/open.pdf) | OpenFlow, control plane/data plane separation, NFV orchestration, network slicing, P4 language, OpenDaylight, scalability bottlenecks |
| [Beyond 5G: Architectural Innovations for Terahertz Communication and Network Slicing](examples/Networking_and_Internet_Architecture/network.pdf) | network slicing, MEC (Multi-access Edge Computing), beamforming, mmWave, URLLC (Ultra-Reliable Low-Latency Communication), O-RAN, energy efficiency |
| [IoT Network Protocols: A Comparative Study of LoRaWAN, NB-IoT, and Thread](examples/Networking_and_Internet_Architecture/LPWAN.pdf) | LPWAN, LoRa, ZigBee 3.0, 6LoWPAN, TDMA scheduling, RPL routing, device density management |
| [Edge Caching in Content Delivery Networks: Algorithms and Economic Incentives](examples/Networking_and_Internet_Architecture/CDN.pdf) | CDN, Akamai, cache replacement policies, DASH (Dynamic Adaptive Streaming), QoE optimization, edge server placement, bandwidth cost reduction |
| [A survey on  flow batteries](examples/Other/battery.pdf)    | battery electrolyte formulation                              |
| [Research on battery electrolyte formulation](examples/Other/flow_battery.pdf) | flow batteries                                               |

## 📃SurveyX 인용

이 프로젝트가 여러분의 프로젝트나 논문에 도움이 되었다면 아래와 같이 인용해 주세요:

```plain text
@misc{liang2025surveyxacademicsurveyautomation,
      title={SurveyX: Academic Survey Automation via Large Language Models}, 
      author={Xun Liang and Jiawei Yang and Yezhaohui Wang and Chen Tang and Zifan Zheng and Shichao Song and Zehao Lin and Yebin Yang and Simin Niu and Hanyu Wang and Bo Tang and Feiyu Xiong and Keming Mao and Zhiyu li},
      year={2025},
      eprint={2502.14776},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2502.14776}, 
}
```

<hr style="border: 1px solid #ecf0f1;">


## 오픈소스 버전 안내
이 오픈소스 버전의 SurveyX는 간소화된 판입니다. 전적으로 사용자가 제공한 로컬 참고문헌 문서에 의존하며, 다음과 같은 고급 기능은 포함하지 않습니다:
- 키워드 확장 및 필터링 알고리즘
- 멀티모달 이미지 파싱 또는 그림 추출
- 온라인 참고문헌 검색 또는 자동 데이터 수집

이러한 고급 모듈은 MemTensor (Shanghai) Technology Co., Ltd.가 호스팅하는 SurveyX 정식 버전에서만 제공됩니다. 전체 기능을 경험해 보고 싶으시다면 공식 웹사이트를 방문해 주세요: [surveyx.cn](https://surveyx.cn)

질문이나 문제가 있으면 저장소에 이슈를 남겨 주세요.

## ⚠️ 면책 조항

SurveyX는 고급 언어 모델을 사용해 학술 논문 작성을 지원합니다. 다만 생성된 내용은 어디까지나 연구 보조 도구라는 점에 유의해야 합니다. SurveyX는 학술 기준에 대한 완전한 준수를 보장할 수 없으므로, 사용자는 생성된 논문의 정확성을 반드시 직접 검증해야 합니다.
