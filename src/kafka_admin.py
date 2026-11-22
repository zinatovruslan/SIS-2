import argparse
import sys
import time

from kafka import KafkaAdminClient, KafkaConsumer, TopicPartition
from kafka.admin import NewTopic
from kafka.errors import KafkaError, NoBrokersAvailable, TopicAlreadyExistsError, UnknownTopicOrPartitionError

from src import config


def create_admin():
    return KafkaAdminClient(
        bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
        client_id="earthquake-admin",
        request_timeout_ms=10000,
    )


def broker_is_available():
    try:
        admin = create_admin()
    except (NoBrokersAvailable, KafkaError):
        return False
    admin.close()
    return True


def create_topic(topic=config.KAFKA_TOPIC):
    admin = create_admin()
    try:
        admin.create_topics([NewTopic(
            name=topic,
            num_partitions=config.KAFKA_PARTITIONS,
            replication_factor=config.KAFKA_REPLICATION_FACTOR,
        )])
        print(f"Topic '{topic}' created (partitions={config.KAFKA_PARTITIONS}, "
              f"replication factor={config.KAFKA_REPLICATION_FACTOR})")
        created = True
    except TopicAlreadyExistsError:
        print(f"Topic '{topic}' already exists")
        created = False
    finally:
        admin.close()
    return created


def delete_topic(topic=config.KAFKA_TOPIC):
    admin = create_admin()
    try:
        admin.delete_topics([topic])
        print(f"Topic '{topic}' deleted")
    except UnknownTopicOrPartitionError:
        print(f"Topic '{topic}' does not exist")
    finally:
        admin.close()
    for _ in range(20):
        if topic not in list_topics():
            return
        time.sleep(0.5)


def list_topics():
    admin = create_admin()
    try:
        return [name for name in admin.list_topics() if not name.startswith("__")]
    finally:
        admin.close()


def count_messages(topic=config.KAFKA_TOPIC):
    consumer = KafkaConsumer(bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS)
    try:
        partitions = consumer.partitions_for_topic(topic) or set()
        topic_partitions = [TopicPartition(topic, partition) for partition in sorted(partitions)]
        if not topic_partitions:
            return 0, {}
        first = consumer.beginning_offsets(topic_partitions)
        last = consumer.end_offsets(topic_partitions)
        per_partition = {tp.partition: last[tp] - first[tp] for tp in topic_partitions}
        return sum(per_partition.values()), per_partition
    finally:
        consumer.close()


def show_info(topic=config.KAFKA_TOPIC):
    topics = list_topics()
    print(f"Broker: {config.KAFKA_BOOTSTRAP_SERVERS}")
    print(f"Topics: {topics}")
    if topic in topics:
        total, per_partition = count_messages(topic)
        print(f"Topic '{topic}': {total} messages, by partition: {per_partition}")


def parse_args():
    parser = argparse.ArgumentParser(description="Create, reset and check the Kafka topic")
    parser.add_argument("--reset", action="store_true", help="delete the topic and create it again")
    parser.add_argument("--info", action="store_true", help="only show topics and number of messages")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        if args.info:
            show_info()
            return
        if args.reset:
            delete_topic()
        create_topic()
        show_info()
    except NoBrokersAvailable:
        print(f"ERROR: Kafka broker is not available at {config.KAFKA_BOOTSTRAP_SERVERS}. "
              f"Start it with: docker compose up -d")
        sys.exit(1)
    except KafkaError as error:
        print(f"ERROR: Kafka error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
