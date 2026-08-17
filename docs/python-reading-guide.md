# Python 코드 읽기 가이드

이 문서는 프로젝트를 읽는 데 필요한 문법만 설명합니다.

## 타입 힌트

```python
def create_request(message: str) -> dict[str, object]: ...
```

`message: str`은 문자열을 받는다는 뜻이고, `-> dict[str, object]`는 딕셔너리를 반환한다는 뜻입니다. 실행을 강제로 제한하기보다 IDE와 리뷰어가 의도를 이해하도록 돕습니다.

## async와 await

```python
async def call_engine() -> Response:
    response = await client.post(url)
    return response
```

외부 API 응답을 기다리는 동안 서버가 다른 요청을 처리할 수 있게 합니다. 네트워크와 streaming 코드에서 주로 사용합니다.

## Pydantic 모델

```python
class Message(BaseModel):
    role: str
    content: str
```

들어온 JSON을 검증하고 Python 객체로 바꿉니다. 필드가 없거나 타입이 다르면 FastAPI가 422 응답을 만듭니다.

## 의존성 주입

FastAPI의 `Depends`는 인증·설정처럼 여러 endpoint가 공유하는 검사를 함수 바깥으로 분리합니다. 테스트에서는 이 의존성을 가짜 구현으로 교체할 수 있습니다.

## generator와 streaming

`yield`를 사용한 함수는 값을 한 번에 반환하지 않고 차례대로 내보냅니다. SSE에서는 model token을 받는 즉시 client에게 전달하는 데 사용합니다.

## context manager

`with`와 `async with`는 파일이나 HTTP client처럼 사용 후 정리가 필요한 자원을 안전하게 닫습니다.
