"""Choose a processor using a data type supplied by the caller."""
from .strategies import AudioProcessor, MetricsProcessor, Processor, VideoProcessor


class ProcessorFactory:
    def get_processor(self, data_type: str) -> Processor:
        processors = {
            "video": VideoProcessor,
            "audio": AudioProcessor,
            "metrics": MetricsProcessor,
        }
        if data_type not in processors:
            raise ValueError(f"Unsupported data type: {data_type}")
        return processors[data_type]()
