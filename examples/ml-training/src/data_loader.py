"""Data loading and preprocessing utilities."""

import numpy as np
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


class DataLoader:
    """Load and preprocess training data."""

    def __init__(self, config):
        self.config = config
        self.scaler = StandardScaler()

    def load_data(self):
        """Load dataset (using synthetic data for demo)."""
        print("Loading dataset...")

        n_samples = self.config.get('n_samples', 1000)
        n_features = self.config.get('n_features', 20)
        n_classes = self.config.get('n_classes', 2)

        # Generate synthetic classification dataset
        X, y = make_classification(
            n_samples=n_samples,
            n_features=n_features,
            n_informative=n_features // 2,
            n_redundant=n_features // 4,
            n_classes=n_classes,
            random_state=42
        )

        print(f"Generated {n_samples} samples with {n_features} features")
        print(f"Classes: {n_classes}")

        return X, y

    def preprocess(self, X_train, X_test):
        """Preprocess features."""
        print("Preprocessing data...")

        # Fit scaler on training data
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        print("Data normalized")

        return X_train_scaled, X_test_scaled

    def split_data(self, X, y):
        """Split into train and test sets."""
        test_size = self.config.get('test_size', 0.2)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )

        print(f"Train set: {len(X_train)} samples")
        print(f"Test set: {len(X_test)} samples")

        return X_train, X_test, y_train, y_test
