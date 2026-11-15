"""Research dataset browsing, separate from live monitoring."""
from fastapi import APIRouter, HTTPException
from app.data import imports as biologist
from app.data.imports import CATALOG

router = APIRouter(prefix='/api/research', tags=['research'])


@router.get('/datasets')
def datasets():
    return {'notice': biologist.NOTICE, 'datasets': biologist.datasets()}


@router.get('/datasets/{dataset_id}')
def dataset(dataset_id: str, subject_id: str | None = None):
    if dataset_id not in {row['id'] for row in biologist.datasets()}:
        raise HTTPException(404, 'Dataset not found')
    return {'notice': biologist.NOTICE, 'catalog': CATALOG, 'observations': biologist.observations(dataset_id, subject_id)}


@router.get('/crew/{crew_id}')
def crew_research(crew_id: str):
    return {'crew_id': crew_id, 'notice': biologist.NOTICE, 'catalog': CATALOG,
            'datasets': biologist.crew_datasets(crew_id)}
