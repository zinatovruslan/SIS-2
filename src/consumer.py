import json
import sys
import uuid

from kafka import KafkaConsumer
from kafka.errors import KafkaError, NoBrokersAvailable

from src import config

IDLE_TIMEOUT_MS = 10000


def create_consumer():
    # A unique group_id on every run: a group that already committed offsets would
    # continue from the saved offset and receive 0 messages on the second run.
    group_id = f"earthquake-consumer-{uuid.uuid4().hex[:8]}"
    consumer = KafkaConsumer(
        config.KAFKA_TOPIC,
        bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
        group_id=group_id,
        client_id="earthquake-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=IDLE_TIMEOUT_MS,
    )
    print(f"Consumer group: {group_id}")
    return consumer


def consume(consumer, expected):
    records = []
    errors = 0
    for message in consumer:
        try:
            record = json.loads(message.value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            errors += 1
            print(f"  skipped offset {message.offset}: broken message ({type(error).__name__})")
            continue
        records.append(record)
        if expected is not None and len(records) >= expected:
            break
    return records, errors


def save_records(records):
    config.ensure_dirs()
    with open(config.CONSUMED_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=1)


def run():
    producer_stats = config.load_stats("producer")
    expected = producer_stats["published"] if producer_stats else None
    if expected is None:
        print("WARNING: producer stats not found, stopping only by the 10 s idle timeout")
    else:
        print(f"Expected messages (published by producer): {expected}")
    consumer = create_consumer()
    try:
        records, errors = consume(consumer, expected)
    finally:
        consumer.close()
    save_records(records)
    config.save_stats("consumer", {"consumed": len(records), "errors": errors})
    print(f"Consumed: {len(records)}")
    print(f"Errors (broken JSON): {errors}")
    print(f"Saved: {config.CONSUMED_JSON_PATH.name}")
    if expected is not None and len(records) < expected:
        print(f"WARNING: got {len(records)} of {expected} messages (topic has fewer messages)")
    return records, errors


def main():
    try:
        run()
    except NoBrokersAvailable:
        print(f"ERROR: Kafka broker is not available at {config.KAFKA_BOOTSTRAP_SERVERS}. "
              f"Start it with: docker compose up -d")
        sys.exit(1)
    except KafkaError as error:
        print(f"ERROR: Kafka error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
