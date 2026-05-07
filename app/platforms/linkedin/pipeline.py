"""LinkedIn-only pipeline. Model loading, feature extraction, and inference."""

from __future__ import annotations

import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"

import io
import pickle
import base64
from pathlib import Path
from typing import Optional

import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model  # type: ignore
from tensorflow.keras.preprocessing.image import load_img, img_to_array  # type: ignore
from tensorflow.keras.applications.resnet50 import ResNet50, preprocess_input  # type: ignore
from tensorflow.keras.preprocessing.sequence import pad_sequences  # type: ignore
from tensorflow.keras.layers import Layer # type: ignore
from PIL import Image

@tf.keras.utils.register_keras_serializable()
class NotEqual(Layer):
    def __init__(self, **kwargs):
        super(NotEqual, self).__init__(**kwargs)
    def call(self, *args, **kwargs):
        import builtins
        # Usually first arg is the tensor, second might be a scalar? Or inside inputs?
        if len(args) >= 2:
            return tf.math.not_equal(args[0], args[1])
        elif len(args) == 1 and isinstance(args[0], (list, tuple)):
            return tf.math.not_equal(args[0][0], args[0][1])
        elif 'inputs' in kwargs:
            # Fallback
            inputs = kwargs['inputs']
            if isinstance(inputs, (list, tuple)):
                return tf.math.not_equal(inputs[0], inputs[1])
            return tf.math.not_equal(inputs, 0)
        elif len(args) >= 1:
            return tf.math.not_equal(args[0], 0)
        return tf.math.not_equal(args[0], 0)

class LinkedInMLPipeline:
    """Singleton ML pipeline for LinkedIn caption generation."""

    _instance: Optional[LinkedInMLPipeline] = None
    _initialized: bool = False

    def __new__(cls) -> LinkedInMLPipeline:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        # Get the directory where this file lives
        module_dir = Path(__file__).parent

        # Load the trained model
        model_path = module_dir / "linkedin_caption_model.h5"
        self.model = load_model(str(model_path), compile=False, custom_objects={'NotEqual': NotEqual})

        # Load the tokenizer
        tokenizer_path = module_dir / "tokenizer.pkl"
        with open(tokenizer_path, "rb") as f:
            self.tokenizer = pickle.load(f)

        # Load ResNet50 for feature extraction (without top layer)
        self.feature_extractor = ResNet50(include_top=False, pooling="avg")

        # Extract vocab and max length from tokenizer
        self.vocab_size = len(self.tokenizer.word_index) + 1
        self.max_length = 100  # Default; adjust if needed based on your training

        self.__class__._initialized = True

    def extract_image_features(self, image_data: bytes) -> np.ndarray:
        """Extract ResNet50 features from raw image bytes."""
        img = Image.open(io.BytesIO(image_data))
        img = img.convert("RGB")
        img = img.resize((224, 224))
        img_array = img_to_array(img)
        img_array = img_array.reshape((1, 224, 224, 3))
        img_array = preprocess_input(img_array)
        features = self.feature_extractor.predict(img_array, verbose=0)
        return features.flatten()

    def predict_caption(self, image_feature: np.ndarray) -> str:
        """Generate a caption from image features using greedy search."""
        in_text = "startseq"

        for _ in range(self.max_length):
            # Tokenize current text
            sequence = self.tokenizer.texts_to_sequences([in_text])[0]
            sequence = pad_sequences([sequence], maxlen=self.max_length)

            # Predict next word
            yhat = self.model.predict([image_feature.reshape(1, 2048), sequence], verbose=0)
            yhat = np.argmax(yhat)

            # Map index to word
            word = self.tokenizer.index_word.get(yhat)

            if word is None or word == "endseq":
                break

            in_text += " " + word

        return in_text.replace("startseq", "").strip()

    def decode_base64_image(self, base64_str: str) -> bytes:
        """Decode base64 string to image bytes."""
        try:
            # Remove data URI scheme if present
            if "," in base64_str:
                base64_str = base64_str.split(",")[1]
            return base64.b64decode(base64_str)
        except Exception as exc:
            raise ValueError(f"Failed to decode base64 image: {exc}") from exc


# Lazy-load the singleton instance
_pipeline_instance: Optional[LinkedInMLPipeline] = None


def get_pipeline() -> LinkedInMLPipeline:
    """Get or initialize the ML pipeline singleton."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = LinkedInMLPipeline()
    return _pipeline_instance
