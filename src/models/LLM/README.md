# src.modules.LLM

## 파일 구조
```
LLM/
├── ChatAgent.py
├── __init__.py
├── README.md
└── utils.py
```

## 파일 설명
### ChatAgent.py
`ChatAgent` 클래스의 구현체.

주요 기능:
- **원격 대화 (`remote_chat`)**: 원격 LLM API에 요청을 보내고 응답을 반환한다. 재시도와 토큰 사용량 추적을 지원한다.
- **배치 원격 대화 (`batch_remote_chat`)**: 멀티스레딩으로 여러 프롬프트를 원격 LLM에 동시에 보낸다.
- **로컬 대화 (`local_chat`)**: 로컬에 띄운 LLM에 질의를 보내고 응답을 반환한다.
- **배치 로컬 대화 (`batch_local_chat`)**: 스레드 풀을 사용해 여러 로컬 LLM 질의를 동시에 처리한다.
- **비용 추적 (`update_cost`, `get_cost`, `get_all_cost`)**: 토큰 사용량을 기준으로 LLM 사용 비용을 추적하고 갱신한다.

### EmbedAgent.py
`EmbedAgent` 클래스의 구현체.

## 주요 기능:
- **원격 임베딩 (`remote_embed`)**: 원격 API에 요청을 보내 주어진 텍스트의 임베딩을 생성한다. 재시도와 선택적 디버그 정보를 지원한다.
- **배치 원격 임베딩 (`batch_remote_embed`)**: 멀티스레딩으로 여러 텍스트를 동시에 처리해 원격 API로 임베딩을 요청한다.
