# Processing: factory and strategies

The factory selects a processor; the processor handles transformation for that data type.

```text
Caller chooses data type
          ↓
ProcessorFactory.get_processor("video" / "audio" / "metrics")
          ↓
VideoProcessor / AudioProcessor / MetricsProcessor
          ↓
processor.process(data)
```

All three processors currently return their input unchanged. They provide a place to add transformations once we choose models. There are no request wrappers, data-type enums, injected adapters, or processing-specific validation yet.

**Video is connected:** `POST /api/video` saves the uploaded file, selects the video processor, passes the saved path through it, then passes its output to the existing placeholder `run_model()`. The response format is unchanged. Audio and metrics have skeleton processors but no endpoints or model integration yet.

```python
from app.processing import ProcessorFactory

processor = ProcessorFactory().get_processor("metrics")
result = processor.process({"heart_rate": 72})
# For now: {"heart_rate": 72}
```

Unsupported data types raise `ValueError`. The input and output formats of each processor can be defined when its real transformation is implemented. Video currently accepts and returns a saved file path because that is what the existing model expects.

### Food for thought: separate endpoints

We could eventually expose `/api/video`, `/api/audio`, and `/api/metrics`. Each endpoint would know the data type and select its processor internally. The client would not need to send a `modality` or `data_type` field. Only `/api/video` exists today; the others are ideas for future integration.

From `backend/`, run the processing tests:

```bash
.venv/bin/python -m unittest discover -s tests -p test_processing.py -v
```

To debug, set breakpoints in the factory or processors, then right-click `backend/tests/test_processing.py` in PyCharm and choose **Debug**. The same file serves testing and debugging.
