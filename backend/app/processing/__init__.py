"""Optional processing layer; not yet connected to the video upload route."""
from .contracts import InputData, Modality, PredictionRequest, Processor
from .factory import ProcessorFactory
from .strategies import AudioProcessor, MetricsProcessor, VideoProcessor

__all__ = [
    "InputData", "Modality", "PredictionRequest", "Processor", "ProcessorFactory",
    "AudioProcessor", "MetricsProcessor", "VideoProcessor",
]
