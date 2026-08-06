import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from tqdm import tqdm

from src.configs.config import (
    DEFAULT_EMBED_LOCAL_MODEL,
    DEFAULT_EMBED_ONLINE_MODEL,
    EMBED_REMOTE_URL,
    EMBED_TOKEN,
)
from src.configs.logger import get_logger

logger = get_logger("src.models.LLM.EmbedAgent")


class EmbedAgent:
    """
    지정한 API를 사용해 원격 텍스트 임베딩을 처리하는 클래스.
    배치 처리를 위한 멀티스레딩을 지원한다.
    """

    def __init__(self, token=EMBED_TOKEN, remote_url=EMBED_REMOTE_URL) -> None:
        """
        EmbedAgent를 초기화한다.

        Args:
            token (str): 원격 API 인증 토큰.
            remote_url (str): 원격 임베딩 API의 URL.
        """
        self.remote_url = remote_url
        self.token = token
        self.header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        try:
            self.local_embedding_model = HuggingFaceEmbedding(
                model_name=DEFAULT_EMBED_ONLINE_MODEL
            )
        except Exception as e:
            logger.info(
                f"{e}\nFailed to load embedding model {DEFAULT_EMBED_ONLINE_MODEL}, try to use local model {DEFAULT_EMBED_LOCAL_MODEL}."
            )
            self.local_embedding_model = HuggingFaceEmbedding(
                model_name=DEFAULT_EMBED_LOCAL_MODEL
            )

    def remote_embed(
        self,
        text: str,
        max_try: int = 15,
        debug: bool = False,
        model: str = "BAAI/bge-m3",
    ) -> list:
        """
        원격 API를 사용해 텍스트를 임베딩한다.

        Args:
            text (str): 임베딩할 입력 텍스트.
            max_try (int, optional): 최대 재시도 횟수.
            debug (bool, optional): 디버그 정보를 함께 반환할지 여부.
            model (str, optional): 원격 API에서 사용할 모델 이름.

        Returns:
            list: 임베딩 벡터 또는 오류 메시지.
        """
        url = self.remote_url
        json_data = json.dumps(
            {"model": model, "input": text, "encoding_format": "float"}
        )

        try:
            response = requests.post(url, headers=self.header, data=json_data)
        except Exception as e:
            logger.error(f"Initial request failed: {e}")
            response = None
            for attempt in range(max_try):
                try:
                    response = requests.post(url, headers=self.header, data=json_data)
                    if response.status_code == 200:
                        logger.info(f"Retry {attempt + 1}/{max_try} succeeded.")
                        break
                except Exception as e:
                    logger.error(f"Retry {attempt + 1}/{max_try} failed: {e}")
                    response = None

        if response is None:
            error_msg = "embed response code: 000"
            if debug:
                return error_msg, response
            return []

        if response.status_code != 200:
            error_msg = f"embed response code: {response.status_code}\n{response.text}"
            logger.error(error_msg)
            if debug:
                return error_msg, response
            return []

        try:
            res = response.json()
            embedding = res["data"][0]["embedding"]
            if debug:
                return embedding, response
            return embedding
        except json.JSONDecodeError as e:
            logger.error(f"JSON decoding failed: {e}")
            if debug:
                return "JSON decoding failed", response
            return []

    def __remote_embed_task(self, index: int, text: str):
        """
        스레드에서 임베딩 작업을 처리하는 내부 메서드.

        Args:
            index (int): 입력 리스트에서 해당 텍스트의 인덱스.
            text (str): 임베딩할 텍스트.

        Returns:
            tuple: (index, embedding)
        """
        embedding = self.remote_embed(text)
        return index, embedding

    def batch_remote_embed(
        self, texts: list[str], worker: int = 10, desc: str = "Batch Embedding..."
    ) -> list:
        """
        멀티스레딩으로 텍스트 임베딩을 배치 처리한다.

        Args:
            texts (list[str]): 임베딩할 텍스트 리스트.
            worker (int, optional): 워커 스레드 개수.
            desc (str, optional): 진행률 표시줄에 표시할 설명.

        Returns:
            list: 임베딩 벡터 리스트.
        """
        embeddings = ["no response"] * len(texts)
        with ThreadPoolExecutor(max_workers=worker) as executor:
            future_l = [
                executor.submit(self.__remote_embed_task, i, texts[i])
                for i in range(len(texts))
            ]
            for future in tqdm(
                as_completed(future_l),
                desc=desc,
                total=len(future_l),
                dynamic_ncols=True,
            ):
                i, embedding = future.result()
                embeddings[i] = embedding
        return embeddings

    def local_embed(self, text: str) -> list[float]:
        embedding = self.local_embedding_model.get_text_embedding(text)
        return embedding

    def batch_local_embed(self, text_l: list[str]) -> list[list[float]]:
        embed_documents = self.local_embedding_model.get_text_embedding_batch(
            text_l, show_progress=True
        )
        return embed_documents


if __name__ == "__main__":
    text_list = ["text1", "text2", "text4"]
    embed_agent = EmbedAgent()
    embedding = embed_agent.batch_remote_embed(text_list)
    print(embedding)
    logger.info("Embedding complete.")

    embedding = embed_agent.batch_local_embed(text_list)
    print(embedding)
