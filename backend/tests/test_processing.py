import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.processing import (
    AudioProcessor, InputData, MetricsProcessor, Modality, ProcessorFactory, VideoProcessor,
)


class ProcessingTests(unittest.TestCase):
    def test_factory_routes_explicit_modalities(self):
        factory = ProcessorFactory()
        for modality, expected in [('video', VideoProcessor), ('audio', AudioProcessor),
                                   ('metrics', MetricsProcessor)]:
            self.assertIsInstance(factory.get_processor(modality), expected)
        with self.assertRaises(ValueError):
            factory.get_processor('unknown')

    def test_metrics_envelope_and_copy(self):
        source = {'heart_rate': 72, 'temperature': 36.5}
        data = InputData('req-1', Modality.METRICS, source, 'A-07')
        result = MetricsProcessor().process(data).to_dict()
        source['heart_rate'] = 0
        self.assertEqual(result, {'request_id': 'req-1', 'modality': 'metrics',
                                 'astronaut_id': 'A-07',
                                 'payload': {'metrics': {'heart_rate': 72.0, 'temperature': 36.5}}})

    def test_invalid_metrics(self):
        for source in [{}, {'x': True}, {'x': '72'}, {'x': math.nan},
                       {'x': math.inf}, {'': 1}, {1: 1}, {'x': 10**400}, Path('x')]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                MetricsProcessor().process(InputData('r', Modality.METRICS, source))

    def test_request_identity_required(self):
        for request_id in ['', ' ', None]:
            with self.assertRaises(ValueError):
                InputData(request_id, Modality.METRICS, {'x': 1})

    def test_modality_mismatch(self):
        with self.assertRaises(ValueError):
            MetricsProcessor().process(InputData('r', Modality.VIDEO, Path('x.mp4')))
        with self.assertRaises(ValueError):
            VideoProcessor().process(InputData('r', Modality.AUDIO, Path('x.wav')))

    def test_media_adapters_and_metadata(self):
        with TemporaryDirectory() as directory:
            for modality in [Modality.VIDEO, Modality.AUDIO]:
                # Both modalities allow WebM; the declared modality determines routing.
                path = Path(directory) / 'clip.webm'
                path.write_bytes(b'test fixture, not encoded media')
                calls = []
                def adapter(source):
                    calls.append(source)
                    return {'features': [1, 2]}
                factory = ProcessorFactory(video_adapter=adapter, audio_adapter=adapter)
                request = factory.get_processor(modality).process(InputData('r', modality, path, 'A'))
                self.assertEqual(calls, [path])
                self.assertEqual(request.payload, {'features': [1, 2]})
                self.assertEqual(request.astronaut_id, 'A')
                self.assertEqual(request.modality, modality)
                with self.assertRaises(NotImplementedError):
                    ProcessorFactory().get_processor(modality).process(InputData('r', modality, path))

    def test_media_validation_before_adapter(self):
        with TemporaryDirectory() as directory:
            empty = Path(directory) / 'empty.mp4'
            empty.touch()
            def unexpected(source):
                self.fail('Adapter must not run for invalid input')
            processor = VideoProcessor(unexpected)
            for source in [empty, Path(directory) / 'missing.mp4', Path(directory), 'clip.mp4']:
                with self.subTest(source=source), self.assertRaises(ValueError):
                    processor.process(InputData('r', Modality.VIDEO, source))

    def test_adapter_payload_must_be_dictionary(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'clip.wav'
            path.write_bytes(b'fixture')
            processor = AudioProcessor(lambda source: None)
            with self.assertRaises(TypeError):
                processor.process(InputData('r', Modality.AUDIO, path))

    def test_registration_is_local(self):
        first, second = ProcessorFactory(), ProcessorFactory()
        replacement = MetricsProcessor()
        first.register('metrics', replacement)
        self.assertIs(first.get_processor('metrics'), replacement)
        self.assertIsNot(second.get_processor('metrics'), replacement)


if __name__ == '__main__':
    unittest.main()
