"""Neural network model definition."""

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier


class MultiLayerModel:
    """Simple multi-layer model wrapper."""

    def __init__(self, config):
        self.config = config
        self.model_type = config.get('model_type', 'mlp')

        if self.model_type == 'mlp':
            self.model = MLPClassifier(
                hidden_layer_sizes=config.get('hidden_layers', (100, 50)),
                max_iter=config.get('max_iter', 100),
                random_state=42,
                verbose=True
            )
        elif self.model_type == 'rf':
            self.model = RandomForestClassifier(
                n_estimators=config.get('n_estimators', 100),
                max_depth=config.get('max_depth', 10),
                random_state=42,
                verbose=1
            )
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

    def train(self, X_train, y_train):
        """Train the model."""
        print(f"Training {self.model_type} model...")
        print(f"Training samples: {len(X_train)}")
        print(f"Features: {X_train.shape[1]}")

        self.model.fit(X_train, y_train)

        train_score = self.model.score(X_train, y_train)
        print(f"Training accuracy: {train_score:.4f}")

        return self

    def evaluate(self, X_test, y_test):
        """Evaluate the model."""
        print("\nEvaluating model...")
        test_score = self.model.score(X_test, y_test)
        print(f"Test accuracy: {test_score:.4f}")

        return {
            'test_accuracy': test_score,
            'model_type': self.model_type
        }

    def predict(self, X):
        """Make predictions."""
        return self.model.predict(X)

    def save(self, path):
        """Save model to disk."""
        import pickle
        with open(path, 'wb') as f:
            pickle.dump(self.model, f)
        print(f"\nModel saved to {path}")
