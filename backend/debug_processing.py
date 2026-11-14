"""Debug this file in PyCharm; step into get_processor() and process()."""
from app.processing import ProcessorFactory


if __name__ == "__main__":
    processor = ProcessorFactory().get_processor("metrics")
    print(f"Selected: {type(processor).__name__}")
    result = processor.process({"heart_rate": 72})
    print(result)
