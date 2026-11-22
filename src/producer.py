import json
import sys

from kafka import KafkaProducer
from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from src import config
from src.api_client import ApiError, fetch_earthquakes
from src.kafka_admin import create_topic


def load_records():
    if config.RAW_JSON_PATH.exists():
        with open(config.RAW_JSON_PATH, encoding="utf-8") as file:
            records = json.load(file)
        print(f"Loaded {len(records)} records from {config.RAW_JSON_PATH.name}")
        return records
    print(f"{config.RAW_JSON_PATH.name} not found, collecting data from the API")
    return fetch_earthquakes()


def create_producer():
    return KafkaProducer(
        bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
        client_id="earthquake-producer",
        key_serializer=lambda key: key.encode("utf-8"),
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        acks="all",
        retries=3,
        linger_ms=10,
    )


def publish(producer, records, topic):
    futures = []
    failed = 0
    for record in records:
        try:
            futures.append(producer.send(topic, key=record["id"], value=record))
        except (KafkaTimeoutError, KafkaError, TypeError, ValueError) as error:
            failed += 1
            print(f"  could not send {record.get('id')}: {error}")
    producer.flush()
    published = 0
    offsets = []
    for future in futures:
        try:
            metadata = future.get(timeout=10)
            published += 1
            offsets.append(metadata.offset)
        except KafkaError as error:
            failed += 1
            print(f"  message was not delivered: {error}")
    return published, failed, offsets


def run():
    records = load_records()
    topic = config.KAFKA_TOPIC
    create_topic(topic)
    producer = create_producer()
    try:
        published, failed, offsets = publish(producer, records, topic)
    finally:
        producer.close()
    stats = {
        "records_read": len(records),
        "published": published,
        "failed": failed,
        "topic": topic,
        "first_offset": min(offsets) if offsets else None,
        "last_offset": max(offsets) if offsets else None,
    }
    config.save_stats("producer", stats)
    print(f"Topic: {topic}, offsets {stats['first_offset']}..{stats['last_offset']}")
    print(f"Published: {published}, Failed: {failed}")
    return stats


def main():
    try:
        run()
    except NoBrokersAvailable:
        print(f"ERROR: Kafka broker is not available at {config.KAFKA_BOOTSTRAP_SERVERS}. "
              f"Start it with: docker compose up -d")
        sys.exit(1)
    except ApiError as error:
        print(f"ERROR: {error}")
        sys.exit(1)
    except KafkaError as error:
        print(f"ERROR: Kafka error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
