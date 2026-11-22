# Global Earthquake Pipeline (SIS 2)

End-to-end data pipeline: **USGS Earthquake API → Kafka Producer → Kafka topic `earthquakes` → Kafka Consumer → Pandera validation → pandas/NumPy cleaning → SQLite3 → EDA (Matplotlib)**.

Course: Data Collection & Preparation. Group: Tuimebayev Doszhan, Shoibek Arman, Akhmetova Kamila, Zinatov Ruslan.

## 1. Overview

| Stage | Module | Input → Output |
|---|---|---|
| Collection | `src/api_client.py` | USGS API → `data/raw_earthquakes.json/.csv` |
| Topic setup | `src/kafka_admin.py` | creates / resets topic `earthquakes` |
| Producer | `src/producer.py` | raw JSON → Kafka topic |
| Consumer | `src/consumer.py` | Kafka topic → `data/consumed_earthquakes.json` |
| Validation | `src/validator.py` | consumed JSON → `data/valid_records.csv`, `data/invalid_records.csv` |
| Cleaning | `src/cleaner.py` | valid CSV → `data/cleaned_earthquakes.csv` |
| Loading | `src/loader.py` | cleaned CSV → `data/earthquakes.db` (SQLite) |
| Analysis | `src/analysis.py` | SQLite → `figures/*.png` |
| Orchestration | `main.py` | runs all stages and prints the final count table |

Every stage reads the output of the previous stage. Statistics of every stage are saved to `data/stats/*.json`.

## 2. Requirements

- Python 3.11+
- Docker Desktop (runs the real Apache Kafka 3.7.0 broker, KRaft mode)
- Free port 9092
- Internet access (USGS API, no API key needed)

## 3. Installation

```bash
git clone https://github.com/zinatovruslan/SIS-2.git
cd SIS-2
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Kafka broker and topic

```bash
docker compose up -d               # start the broker
docker ps                          # wait for: kafka ... (healthy)
python -m src.kafka_admin --reset  # create an empty topic `earthquakes`
python -m src.kafka_admin --info   # show topics and number of messages
```

Topic configuration: name `earthquakes`, 1 partition, replication factor 1, topic auto-creation disabled in the broker (the topic is created by `src/kafka_admin.py`). Message key = earthquake id (UTF-8), value = one record as JSON (UTF-8).
Broker address: `localhost:9092` (change with the `KAFKA_BOOTSTRAP_SERVERS` environment variable).

Stop the broker: `docker compose down` (topic data is deleted).

## 5. API configuration

USGS Earthquake Catalog API (FDSN Event Web Service): `https://earthquake.usgs.gov/fdsnws/event/1/query`. No key or secrets are needed. Default parameters are in `src/config.py`: period 2026-10-01 – 2026-11-01, minimum magnitude 2.5. They can be changed without editing code:

```bash
python -m src.api_client --start 2026-10-01 --end 2026-11-01 --min-mag 4
```

## 6. Run the complete pipeline

One command (broker must be running):

```bash
python main.py
```

Or stage by stage, in this order:

```bash
python -m src.kafka_admin --reset      # clean topic
python -m src.api_client               # 1. collect data
python -m src.producer                 # 2. publish to Kafka
python -m src.consumer                 # 3. consume from Kafka
python -m src.validator                # 4. Pandera validation
python -m src.cleaner                  # 5. cleaning and transformation
python -m src.loader --idempotency-test  # 6. load into SQLite (twice, no duplicates)
python -m src.analysis                 # 7. EDA and figures
```

Run the producer only once per clean topic. Without `--reset` a second run puts every record into the topic twice (5030 messages).

## 7. Validation testing

```bash
python -m src.validator --test         # injects invalid records TEST_..., checks that Pandera catches them
python -m src.validator                # run again: valid_records.csv without test records
```

Do not use `--test` inside `main.py`.

## 8. Database generation and verification

```bash
python -m src.loader                   # create the database and load the data
python -m src.loader --verify          # SQL verification queries (the same queries are in sql/verification_queries.sql)
python -m src.loader --idempotency-test  # load twice, the number of rows must not change
```

## 9. Analysis and figures

```bash
python -m src.analysis
```

Reads the table `earthquakes` from `data/earthquakes.db`, prints statistics and saves figures to `figures/`:
`magnitudes_hist.png`, `magnitude_depth_scatter.png`, `top_regions_bar.png`, `earthquakes_by_day_line.png`, `correlation_heatmap.png`. A short finding for each figure is printed to the console and saved in `data/stats/analysis.json`.

## 10. Expected output

The numbers depend on the moment of the API request (USGS adds and revises events), so they are not fixed. `main.py` ends with a table built from `data/stats/*.json`: collected, published, consumed, valid, invalid, after cleaning, stored in SQLite and stored after the second load. Expected relations:

- collected = published = consumed;
- consumed = valid + invalid;
- after cleaning = valid - duplicates - records removed by the filter (`status = reviewed`, `mag >= 3.0`, `sig >= 50`);
- stored in SQLite = after cleaning; the second load gives the same number (no duplicates).

## 11. How to verify success

1. `python -m src.kafka_admin --info` shows a number equal to the collected records in the topic.
2. `data/stats/*.json` exist for api, producer, consumer, validator, cleaner, loader.
3. `python -m src.loader --verify` shows that `COUNT(*) = COUNT(DISTINCT id)`.
4. `python -m src.loader --idempotency-test` shows the same row count after the second load.
5. Five `.png` files exist in `figures/`.

## 12. Troubleshooting

| Problem | Solution |
|---|---|
| `Kafka broker is not available at localhost:9092` | `docker compose up -d`, wait until `docker ps` shows `healthy` |
| Port 9092 is busy | stop the other Kafka or application that uses the port |
| Consumer got 0 messages | the producer was not run after `--reset`; run `python -m src.producer` |
| 5030 messages in the topic | the producer was run twice; run `python -m src.kafka_admin --reset` |
| `ModuleNotFoundError: src` | run commands from the repository root with `python -m src.<module>` |

## 13. Project structure

```
SIS-2/
├── README.md, requirements.txt, docker-compose.yml, main.py, .gitignore
├── src/        config, api_client, kafka_admin, producer, consumer, validator, cleaner, loader, analysis
├── sql/        verification_queries.sql
├── data/       raw / consumed / valid / cleaned files, earthquakes.db, stats/
├── figures/    generated charts
├── docs/       data_dictionary.md
└── report/     project_report.pdf
```
