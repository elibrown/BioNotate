"""Prepare homogeneous trend series and descriptive change; no clinical inference."""
from app import db
import json

_CONFIG = json.loads((db.DATA_DIR / 'biomarkers.json').read_text())
_META = {v['measurement_metric']: v for v in _CONFIG['metrics'].values()}
_ALIASES = _CONFIG.get('metric_aliases', {})
_UNITS = _CONFIG.get('unit_aliases', {})


def measurement_trends(astronaut_id: str, metric: str | None = None,
                       source: str | None = None, context: str | None = None,
                       dataset_id: str | None = None) -> list[dict]:
    """One trend read path for every metric and source in production measurements."""
    grouped = {}
    for row in db.list_measurements(astronaut_id=astronaut_id, metric=None, source=source,
                                 context=context, dataset_id=dataset_id, limit=10000):
        row['stored_metric'] = row['metric']
        row['metric'] = _ALIASES.get(row['metric'], row['metric'])
        row['unit'] = _UNITS.get(row['unit'], row['unit'])
        if metric is not None and row['metric'] != _ALIASES.get(metric, metric):
            continue
        axis = 'mission_phase' if row['phase_index'] is not None else 'timestamp'
        key = (row['metric'], row['unit'], row['source'], row['context'], row['dataset_id'], axis)
        series = grouped.setdefault(key, {
            'metric': row['metric'], 'label': _META.get(row['metric'], {}).get('label', row['metric'].replace('_', ' ').title()),
            'unit': row['unit'], 'source': row['source'],
            'context': row['context'], 'dataset_id': row['dataset_id'], 'axis': axis, 'points': []})
        series['points'].append(row)
    for series in grouped.values():
        points = series['points']
        values = [point['value'] for point in points]
        delta = values[-1] - values[0] if len(values) >= 2 else None
        series['summary'] = {
            'count': len(values), 'first': values[0], 'latest': values[-1],
            'minimum': min(values), 'maximum': max(values), 'delta': delta,
            'percent_change': (delta / abs(values[0]) * 100) if delta is not None and values[0] else None,
            'direction': ('insufficient_data' if delta is None else
                          'rising' if delta > 0 else 'falling' if delta < 0 else 'unchanged'),
        }
    return list(grouped.values())
