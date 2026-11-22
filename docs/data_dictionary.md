# Data dictionary

Table `earthquakes` in `data/earthquakes.db`. Source: USGS Earthquake Catalog API (https://earthquake.usgs.gov/fdsnws/event/1/).

| Column | SQLite type | Kind | Description |
|---|---|---|---|
| id | TEXT, PRIMARY KEY | identifier | Unique USGS event id |
| mag | REAL, NOT NULL | numerical | Magnitude |
| mag_type | TEXT, NOT NULL | categorical | Magnitude type (ml, mb, mww, ...), lower case |
| place | TEXT, NOT NULL | text | Description of the location |
| region | TEXT | categorical | Region/country extracted from `place` |
| time_utc | TEXT, NOT NULL | date/time | Event time, UTC, ISO format `YYYY-MM-DDTHH:MM:SSZ` |
| updated_utc | TEXT, NOT NULL | date/time | Last update of the record in USGS, UTC |
| latitude | REAL, NOT NULL | numerical | Latitude, degrees |
| longitude | REAL, NOT NULL | numerical | Longitude, degrees |
| depth_km | REAL, NOT NULL | numerical | Depth of the event, km |
| depth_band | TEXT, NOT NULL | categorical | shallow (<70 km), intermediate (70-300 km), deep (>=300 km); derived with `np.select` |
| sig | REAL | numerical | USGS significance score |
| tsunami | INTEGER, NOT NULL | categorical | 1 if a tsunami flag is set, otherwise 0 (CHECK constraint) |
| status | TEXT, NOT NULL | categorical | reviewed / automatic (after cleaning: reviewed only) |
| alert | TEXT | categorical | PAGER alert level, `none` if not issued |
| net | TEXT | categorical | Contributing seismic network |
| distance_from_equator_km | REAL | numerical | Derived by NumPy: abs(latitude in radians) * 6371 |
| energy_log10_j | REAL | numerical | Derived: 1.5 * mag + 4.8 (log10 of energy, joules) |
| severity_score | REAL | numerical | Derived: magnitude scaled to 0..1 (min-max) |
| loaded_at | TEXT | date/time | Time of insertion into the database |

Cleaning filter applied before loading: `status == "reviewed"`, `mag >= 3.0`, `sig >= 50`.
