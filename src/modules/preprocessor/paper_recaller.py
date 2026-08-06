import random
from typing import Dict, List

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_distances

from src.configs.config import (
    BASE_DIR,
    DEFAULT_ITERATION_LIMIT,
    DEFAULT_PAPER_POOL_LIMIT,
)
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent
from src.models.LLM import EmbedAgent
from src.models.LLM.utils import load_prompt
from src.modules.preprocessor.data_cleaner import DataCleaner
from src.modules.preprocessor.data_fetcher import DataFetcher
from src.configs.config import DEFAULT_DATA_FETCHER_ENABLE_CACHE

logger = get_logger("src.modules.preprocessor.PaperRecaller")


class PaperRecaller:
    """
    진화하는 키워드를 기반으로 논문을 반복적으로 리콜하고 처리하는 클래스.
    """

    def __init__(
        self,
        topic: str,
        iteration_limit: int = DEFAULT_ITERATION_LIMIT,
        paper_pool_limit: int = DEFAULT_PAPER_POOL_LIMIT,
        enable_cache: bool = DEFAULT_DATA_FETCHER_ENABLE_CACHE,
        chat_agent: ChatAgent = None,
    ):
        """
        PaperRecaller를 초기화한다.

        Args:
            key_word_pool (List[str]): 초기 키워드 풀.
            iteration_limit (int): 최대 반복 횟수.
            paper_pool_limit (int): 풀에 유지할 최대 논문 수.
        """

        self.iteration_limit = iteration_limit
        self.paper_pool_limit = paper_pool_limit

        self.data_fetcher = DataFetcher(enable_cache=enable_cache)
        self.embed_agent = EmbedAgent()
        self.chat_agent = ChatAgent() if chat_agent is None else chat_agent

        self.paper_pool: List[Dict] = []
        self.keyword_pool: List[str] = []
        self.existing_keyword_embeddings: np.ndarray = np.array(
            self.embed_agent.batch_local_embed([topic])
        ).astype(float)

        if not isinstance(self.existing_keyword_embeddings, np.ndarray):
            self.existing_keyword_embeddings = np.array(
                [self.existing_keyword_embeddings]
            )

    def _search_papers(
        self, keyword: str, page: str, time_s: str, time_e: str
    ) -> List[Dict]:
        """
        Google Scholar와 arXiv에서 논문을 검색한다.

        Args:
            keyword (str): 검색할 키워드.

        Returns:
            List[Dict]: 논문 딕셔너리 리스트.
        """
        logger.debug(
            f"Searching papers on google: key word={keyword}, page={page}, time_s={time_s}, time_e={time_e}."
        )
        google_papers = self.data_fetcher.search_on_google(
            key_words=keyword, page=page, time_s=time_s, time_e=time_e
        )
        logger.debug(f"Searching papers on arxiv: key word={keyword}.")
        arxiv_papers = self.data_fetcher.search_on_arxiv(key_words=keyword)
        combined_papers = google_papers + arxiv_papers
        logger.debug(
            f"Total papers retrieved from google scholar & arxiv: {len(combined_papers)}"
        )
        return combined_papers

    def _clean_paper_pool(self, new_papers: List[Dict]):
        """
        유효하지 않은 항목을 제거하고 중복을 없애 논문 풀을 정리한다.

        Args:
            new_papers (List[Dict]): 새로 가져온 논문들.
        """
        logger.debug("Cleaning and deduplicating paper pool.")

        # 논문 필터링
        dc = DataCleaner(new_papers)
        valid_papers = dc.quick_check()
        logger.debug(f"Papers after filtering empty fields: {len(valid_papers)}")

        # _id 기준으로 중복 제거
        existing_ids = {paper["_id"] for paper in self.paper_pool}
        unique_papers = [
            paper for paper in valid_papers if paper["_id"] not in existing_ids
        ]
        logger.debug(f"Papers after deduplication: {len(unique_papers)}")

        self.paper_pool.extend(unique_papers)

    def _embed_papers(self):
        """
        임베딩이 없는 새 논문들을 임베딩한다.
        """
        logger.debug("Embedding new papers.")

        # 임베딩이 없는 논문 식별
        new_papers = [paper for paper in self.paper_pool if "embedding" not in paper]
        logger.debug(f"Papers to embed: {len(new_papers)}")

        if not new_papers:
            logger.debug("No new papers to embed.")
            return

        # 임베딩할 초록 추출
        texts = [
            ("Title: " + paper["title"] + "\nAbstract: " + paper["abstract"])
            for paper in new_papers
        ]
        embeddings = self.embed_agent.batch_local_embed(texts)

        # 임베딩을 할당하거나, 임베딩에 실패한 논문은 제거
        for paper, embedding in zip(new_papers, embeddings):
            if (
                isinstance(embedding, list) and embedding
            ):  # "no response"와 [] 걸러내기
                paper["embedding"] = embedding
            else:
                logger.warning(
                    f"Embedding failed for paper: '{paper.get('title', 'No Title')}'. Removing from pool."
                )
                self.paper_pool.remove(paper)

    def _cluster_papers(self) -> List[List[Dict]]:
        """
        임베딩을 기준으로 논문을 클러스터링한다.

        Returns:
            List[List[Dict]]: 각 원소가 논문 리스트인 클러스터들의 리스트.
        """
        logger.debug("Clustering papers based on embeddings.")

        # 임베딩 행렬 준비
        embeddings = np.array([paper["embedding"] for paper in self.paper_pool])
        if embeddings.size == 0:
            logger.warning("No embeddings available for clustering.")
            return []

        num_clusters = len(self.keyword_pool) + 1
        logger.debug(f"Number of clusters to form: {num_clusters}")

        # KMeans 클러스터링 수행
        kmeans = KMeans(n_clusters=num_clusters, random_state=42)
        labels = kmeans.fit_predict(embeddings)

        # 논문을 클러스터별로 정리
        clusters = [[] for _ in range(num_clusters)]
        for label, paper in zip(labels, self.paper_pool):
            clusters[label].append(paper)

        logger.debug("Clustering completed.")
        return clusters

    def _generate_keywords(self, clusters: List[List[Dict]]) -> List[str]:
        """
        ChatAgent를 사용해 각 클러스터에서 키워드를 생성한다.

        Args:
            clusters (List[List[Dict]]): 논문 클러스터들.

        Returns:
            List[str]: 생성된 키워드들.
        """
        logger.debug("Generating keywords from clusters.")

        prompts = []
        for cluster in clusters:
            sampled_papers = random.sample(cluster, min(15, len(cluster)))
            titles = [paper["title"] for paper in sampled_papers]
            abstracts = [paper["abstract"] for paper in sampled_papers]
            if len(self.paper_pool) >= 1000:
                combined_text = "\n".join([f"Title: {t}\n" for t in titles])
            else:
                combined_text = "\n".join(
                    [f"Title: {t}\nAbstract: {a}" for t, a in zip(titles, abstracts)]
                )
            exclude_keywords = ", ".join(self.keyword_pool)
            prompt = load_prompt(
                f"{BASE_DIR}/resources/LLM/prompts/preprocessor/PaperRecall_gen_key_word.md",
                combined_text=combined_text,
                exclude_keywords=exclude_keywords,
            )
            prompts.append(prompt)

        generated_responses = self.chat_agent.batch_remote_chat(prompts)
        generated_keywords = [
            response.strip() for response in generated_responses if response.strip()
        ]

        logger.debug(f"Generated keywords: {generated_keywords}")
        return generated_keywords

    def _select_new_keyword(self, generated_keywords: List[str]) -> str:
        """
        생성된 키워드 중 추가하기에 가장 적절한 새 키워드를 선택한다.

        Args:
            generated_keywords (List[str]): 생성된 키워드 리스트.

        Returns:
            str: 선택된 새 키워드.
        """
        logger.debug("Selecting a new keyword from generated keywords.")

        if not generated_keywords:
            logger.warning("No generated keywords to select from.")
            return ""

        # 생성된 키워드 임베딩
        keyword_embeddings = np.array(
            self.embed_agent.batch_local_embed(generated_keywords)
        ).astype(float)

        # 기존 키워드들과의 거리 계산(두 벡터 집합에 대한 코사인 거리 행렬 반환)
        distances = cosine_distances(
            keyword_embeddings, self.existing_keyword_embeddings
        )

        # 최초 키워드(topic)와의 거리 가중치를 2배로 설정
        weights = np.ones(self.existing_keyword_embeddings.shape[0])
        weights[0] = 2

        avg_distances = np.average(distances, axis=1, weights=weights)
        max_distances = distances.max(axis=1)

        # 가중 평균 거리(내림차순)와 최대 거리(오름차순)를 기준으로 순위 산정
        avg_rank = avg_distances.argsort()[::-1]
        max_rank = max_distances.argsort()

        # 평균 순위 계산
        combined_ranks = []
        for i in range(len(generated_keywords)):
            combined_rank = (
                np.where(avg_rank == i)[0][0] + np.where(max_rank == i)[0][0]
            ) / 2
            combined_ranks.append(combined_rank)

        # 합산 순위가 가장 작은 키워드 선택
        selected_index = np.argmin(combined_ranks)
        new_keyword = generated_keywords[selected_index]

        # 임베딩해 existing_keyword_embeddings에 추가
        new_embedding = keyword_embeddings[selected_index].reshape(1, -1)
        self.existing_keyword_embeddings = np.vstack(
            [self.existing_keyword_embeddings, new_embedding]
        )

        logger.debug(
            f"Selected new keyword: '{new_keyword}' with index {selected_index}"
        )
        return new_keyword

    def deal_init_keywords(self, key_words: str, page: str, time_s: str, time_e: str):
        key_words = key_words.split(",")

        for kw in key_words:
            new_papers = self._search_papers(kw, page, time_s, time_e)
            self._clean_paper_pool(new_papers)
            self.keyword_pool.append(kw)

            if len(self.paper_pool) >= self.paper_pool_limit:
                logger.info(
                    f"Reached paper pool limit of {self.paper_pool_limit}. Stopping recalling."
                )
                break

        logger.info(f"Initialized keywords retrieved  {len(self.paper_pool)} papers.")

    def recall_papers_iterative(
        self, key_word: str, page: str, time_s: str, time_e: str
    ):
        """
        반복적인 논문 리콜과 처리를 수행한다.
        """
        self.deal_init_keywords(key_word, 5, time_s, time_e)

        for iteration in range(1, self.iteration_limit + 1):
            logger.info(f"============= Iteration {iteration} ===============")

            # 모든 논문 임베딩
            self._embed_papers()

            # 논문 클러스터링
            clusters = self._cluster_papers()
            logger.info(f"Formed {len(clusters)} clusters.")

            # 클러스터에서 새 키워드 생성
            generated_keywords = self._generate_keywords(clusters)
            logger.info(f"Generated {len(generated_keywords)} keywords from clusters.")

            # 추가할 가장 적절한 키워드 선택
            new_keyword = self._select_new_keyword(generated_keywords)
            if new_keyword:
                logger.info(f"Selected new keyword: '{new_keyword}'")
                self.keyword_pool.append(new_keyword)
            else:
                logger.warning("No suitable new keyword found. Stopping recalling.")
                break

            # 현재 키워드로 논문 검색
            new_papers = self._search_papers(new_keyword, page, time_s, time_e)
            logger.info(f"Retrieved {len(new_papers)} new papers.")

            # 논문 풀 정리 및 중복 제거
            self._clean_paper_pool(new_papers)
            logger.info(f"Paper pool size after cleaning: {len(self.paper_pool)}")

            if len(self.paper_pool) >= self.paper_pool_limit:
                logger.info(
                    f"Reached paper pool limit of {self.paper_pool_limit}. Stopping recalling."
                )
                break

        logger.info(
            f"Paper recall iterations completed. Total papers in pool: {len(self.paper_pool)}"
        )
        return self.paper_pool


# python -m src.modules.preprocessor.paper_recaller
if __name__ == "__main__":
    pr = PaperRecaller()
    papers = pr.recall_papers_iterative(
        "battery electrolyte formulation", "1", "2016", "2025"
    )
