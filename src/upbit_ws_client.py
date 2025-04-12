import asyncio
from aiokafka import AIOKafkaProducer
import websockets
import orjson # orjson 사용, 없으면 import json 사용
import uuid
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from config import UPBIT_WEBSOCKET_URI, MARKET_CODES, RECONNECT_DELAY_SECONDS, logger
from kafka_producer import send_to_kafka

async def upbit_websocket_client(producer: AIOKafkaProducer) -> None:
    """
    업비트 웹소켓에 연결하고 데이터를 수신하여 Kafka로 전송합니다.
    
    Args:
        producer (AIOKafkaProducer): AIOKafkaProducer 객체
    
    Returns:
        None
    """
    while True:
        try:
            # websockets.connect는 연결 실패 시 자동으로 재시도 (기본 backoff 포함)
            async with websockets.connect(UPBIT_WEBSOCKET_URI, ping_interval=20, ping_timeout=20) as websocket:
                logger.info(f"Successfully connected to Upbit WebSocket: {UPBIT_WEBSOCKET_URI}")

                # 구독 메시지 생성 (고유 티켓 포함)
                subscribe_request = [
                    {"ticket": str(uuid.uuid4())},
                    {"type": "ticker", "codes": MARKET_CODES},
                    {"format": "DEFAULT"} # 또는 "SIMPLE"
                ]
                await websocket.send(orjson.dumps(subscribe_request))
                logger.info(f"Sent subscription request for tickers: {MARKET_CODES}")

                # 데이터 수신 루프
                async for message in websocket:
                    try:
                        # 수신된 데이터는 bytes 타입이므로 orjson/json으로 로드
                        data = orjson.loads(message)
                        logger.debug(f"Received data: {data}")

                        # 'ticker' 타입 데이터만 처리 (필요시 다른 타입도 처리)
                        if data.get('type') == 'ticker':
                            logger.debug(f"Sending Kafka Producer: {data}")
                            await send_to_kafka(producer, data)
                        else:
                            logger.debug(f"Ignoring non-ticker message: {data.get('type')}")

                    except orjson.JSONDecodeError as e:
                        logger.error(f"Failed to decode JSON message: {message}, Error: {e}")
                    except Exception as e:
                        logger.error(f"Error processing received message: {e}")

        except (ConnectionClosedError, ConnectionClosedOK) as e:
            logger.warning(f"WebSocket connection closed: {e}. Attempting to reconnect in {RECONNECT_DELAY_SECONDS} seconds...")
        except websockets.exceptions.InvalidURI as e:
            logger.error(f"Invalid WebSocket URI: {UPBIT_WEBSOCKET_URI}. Error: {e}")
            break # URI가 잘못되면 재시도 의미 없음
        except websockets.exceptions.WebSocketException as e:
             logger.error(f"WebSocket error occurred: {e}. Attempting to reconnect in {RECONNECT_DELAY_SECONDS} seconds...")
        except OSError as e: # 네트워크 관련 OS 에러 (e.g., "Connection refused")
             logger.error(f"Network error: {e}. Attempting to reconnect in {RECONNECT_DELAY_SECONDS} seconds...")
        except Exception as e:
            # 예상치 못한 다른 모든 예외 처리
            logger.error(f"An unexpected error occurred: {e}. Attempting to reconnect in {RECONNECT_DELAY_SECONDS} seconds...")

        # 재연결 시도 전 대기
        await asyncio.sleep(RECONNECT_DELAY_SECONDS)