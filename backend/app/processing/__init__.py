"""Processing skeleton with video connected to the upload route."""
from .factory import ProcessorFactory
from .strategies import AudioProcessor, MetricsProcessor, Processor, VideoProcessor

__all__ = [
    "ProcessorFactory", "Processor", "VideoProcessor", "AudioProcessor", "MetricsProcessor",
]
