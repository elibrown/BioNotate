"""Select strategies by explicit modality, never by ambiguous file extensions."""
from .contracts import Modality, Processor
from .strategies import AudioProcessor, MediaAdapter, MetricsProcessor, VideoProcessor


class ProcessorFactory:
    def __init__(
        self,
        *,
        video_adapter: MediaAdapter | None = None,
        audio_adapter: MediaAdapter | None = None,
    ):
        self._processors: dict[Modality, Processor] = {
            Modality.VIDEO: VideoProcessor(video_adapter),
            Modality.AUDIO: AudioProcessor(audio_adapter),
            Modality.METRICS: MetricsProcessor(),
        }

    def register(self, modality: Modality | str, processor: Processor) -> None:
        """Replace a strategy within this factory, without changing other callers."""
        self._processors[Modality(modality)] = processor

    def get_processor(self, modality: Modality | str) -> Processor:
        return self._processors[Modality(modality)]
