"""Training utilities and helpers."""

import json
import time
from datetime import datetime


class TrainingLogger:
    """Log training progress and metrics."""

    def __init__(self, log_file='training.log'):
        self.log_file = log_file
        self.start_time = None
        self.metrics = {}

    def start(self):
        """Mark training start."""
        self.start_time = time.time()
        print(f"\n{'='*60}")
        print(f"Training started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

    def log_metric(self, name, value):
        """Log a metric."""
        self.metrics[name] = value
        print(f"  {name}: {value}")

    def finish(self):
        """Mark training end and save results."""
        if self.start_time:
            elapsed = time.time() - self.start_time
            self.metrics['training_time_seconds'] = elapsed

            print(f"\n{'='*60}")
            print(f"Training completed in {elapsed:.2f} seconds")
            print(f"{'='*60}\n")

        # Save metrics to file
        with open(self.log_file, 'w') as f:
            json.dump(self.metrics, f, indent=2)

        print(f"Metrics saved to {self.log_file}")

        return self.metrics


def load_config(config_path):
    """Load configuration from JSON file."""
    print(f"Loading config from {config_path}")

    with open(config_path, 'r') as f:
        config = json.load(f)

    print("Configuration loaded:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    print()

    return config


def save_results(results, output_path='results.json'):
    """Save training results."""
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {output_path}")
