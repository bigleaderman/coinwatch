from aiokafka import AIOKafkaProducer
import orjson # orjson 사용, 없으면 import json 사용
from datetime import datetime, timezone
from typing import Dict, Any

from config import KAFKA_BROKERS, KAFKA_TOPIC, logger

async def create_producer() -> AIOKafkaProducer | None:
    """Kafka 프로듀서를 생성하고 시작합니다."""
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BROKERS,
        value_serializer=lambda v: orjson.dumps(v), # orjson 사용
        # value_serializer=lambda v: json.dumps(v).encode('utf-8'), # 표준 json 사용 시
        acks='all', # 모든 ISR로부터 확인 받음 (데이터 유실 방지)
        enable_idempotence=True # 멱등성 활성화 (중복 전송 방지)
    )
    try:
        await producer.start()
        logger.info(f"Kafka producer connected to {KAFKA_BROKERS}")
        return producer
    except Exception as e:
        logger.error(f"Failed to start Kafka producer: {e}")
        return None

async def send_to_kafka(producer: AIOKafkaProducer, data: Dict[str, Any]) -> None:
    """
    수신된 데이터를 Kafka 토픽으로 전송합니다.
    
    Args:
        producer (AIOKafkaProducer): AIOKafkaProducer 인스턴스
        data (Dict[str, Any]): Kafka에 전송할 dict 객체
    """
    try:
        # 데이터 보강: 수신 타임스탬프 추가 (UTC 기준 ISO 형식)
        data['received_timestamp_utc'] = datetime.now(timezone.utc).isoformat()

        # Kafka 메시지 키 설정 (마켓 코드 사용)
        message_key = data.get('code', data.get('cd')) # 'code' 또는 축약형 'cd' 사용
        if message_key:
            key_bytes = message_key.encode('utf-8')
        else:
            key_bytes = None
            logger.warning("Could not determine Kafka message key from data.")

        # Kafka에 메시지 전송 (send_and_wait는 전송 완료 확인)
        future = await producer.send(KAFKA_TOPIC, value=data, key=key_bytes)
        record_metadata = await future # 전송 결과 대기
        logger.debug(f"Message sent to Kafka topic '{KAFKA_TOPIC}': partition={record_metadata.partition}, offset={record_metadata.offset}")
    except Exception as e:
        logger.error(f"Failed to send message to Kafka: {e}")
        # 필요시 여기서 재시도 로직 추가 가능 (AIOKafkaProducer는 내부적으로 재시도)

async def stop_producer(producer: AIOKafkaProducer) -> None:
    """
    Kafka 프로듀서를 안전하게 종료합니다.
    
    Args:
        producer (AIOKafkaProducer): AIOKafkaProducer 인스턴스
    """
    if producer:
        try:
            await producer.stop()
            logger.info("Kafka producer stopped.")
        except Exception as e:
            logger.error(f"Error stopping Kafka producer: {e}")