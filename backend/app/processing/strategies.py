"""One processing skeleton per data type; transformation is still to be defined."""
from abc import ABC, abstractmethod


class Processor(ABC):
    @abstractmethod
    def process(self, data):
        """Transform input into model-ready data once a model is selected."""
        raise NotImplementedError


class VideoProcessor(Processor):
    def process(self, data):
        # TODO: Prepare video for the selected model.
        return data


class AudioProcessor(Processor):
    def process(self, data):
        # TODO: Prepare audio for the selected model.
        return data


class MetricsProcessor(Processor):
    def process(self, data):
        # TODO: Prepare metrics for the selected model.
        return data
